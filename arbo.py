#!/usr/bin/python3 -S
# vim: set fileencoding=utf-8 sw=2 ts=2 et :
from __future__ import absolute_import

import codecs
import itertools
import locale
import argparse
import os
import re
import subprocess
import sys
from arbo_readline0 import readline0

# Used for filesystem root and POSIX alternative root
# Path components otherwise never contain slashes
# These must be handled specially so neither is a prefix of the other
SLASH = '/'
SLASHSLASH = '//'
SPECIALS = (SLASH, SLASHSLASH)

# We parse ls output for efficiency and accuracy.
# Output is escaped so the only escapes and newlines are the ones ls adds.
START_COLOR = '\033'
WITH_COLOR_RE = re.compile(
  r'^(?:\033\[0m)?(\033\[[0-9]+;[0-9]+m)?[^\n\033]*?([^/\n\033]*/*)(?:\033\[(?:0m|K))*\n(?:\033\[m)?$')
END_COLOR = '\033[0m'
END_LS = '\033[m'

# Ways to display a tree
STYLE_ASCII   = ('   ', '|  ', '`- ', '|- ', )
STYLE_UNICODE = ('   ', '│  ', '└─ ', '├─ ', )

# For a wide and short display, pstree-style
WIDE_STYLE_ASCII   = ('   ', '---', '-+-', ' `-', ' | ', ' |-', )
WIDE_STYLE_UNICODE = ('   ', '───', '─┬─', ' └─', ' │ ', ' ├─', )

# How many paths in one ls call
BULK_LS_COUNT = 400


class Node(object):
  """
  A tree node.

  Children is an iterable.
  Value is a path element.
  """

  def __init__(self, value):
    self.value = value
    self.color = None
    self.children = []

  @property
  def pvalue(self):
    if self.color is not None:
      return self.color + self.value + END_COLOR
    return self.value

class NodeTraversal(object):
  def __init__(self, node, parent, is_first_sib, is_last_sib):
    self.node = node
    self.parent = parent
    self.is_first_sib = is_first_sib
    self.is_last_sib = is_last_sib

  @property
  def has_single_child(self):
    return len(self.node.children) == 1

  @property
  def has_children(self):
    return bool(self.node.children)

  @property
  def is_root(self):
    return self.parent is None

  @property
  def path_str(self):
    # Don't use the ROOT node in a path.
    if self.min_depth(2):
      r = self.parent.path_str
      if self.parent not in SPECIALS:
        r += '/'
    else:
      r = ''
    r += self.node.value
    return r

  def min_depth(self, n):
    if n < 0:
      raise ValueError(n, 'must be non-negative')
    if n == 0:
      return True
    # root has depth 0
    if self.is_root:
      return False
    return self.parent.min_depth(n - 1)

  def iter_parents(self, min_depth):
    # XXX there's probably a way to avoid this loop entirely
    a = self.parent
    rev_list = []
    while a is not None and a.min_depth(min_depth):
      rev_list.insert(0, a)
      a = a.parent
    return rev_list


def traverse_tree_skip_root(root):
  """
  Tree traversal, skipping the root.
  """

  root_cursor = NodeTraversal(root, None, True, True)
  for nt in iter_with_first_last(root_cursor):
    for e in traverse_tree(nt):
      yield e

def traverse_tree(nt0):
  """
  Traverse a tree in depth-first order.
  """

  yield nt0

  for nt in iter_with_first_last(nt0):
    for e in traverse_tree(nt):
      yield e

def colorize_nt_iter(itr):
  while True:
    nt_bulk = list(itertools.islice(itr, BULK_LS_COUNT))
    if not nt_bulk:
      return
    postprocess_path(nt_bulk)
    for nt in nt_bulk:
      yield nt

def display_tree(tree_root, out, wide, colorize):
  nt_iter = traverse_tree_skip_root(tree_root)
  if colorize:
    nt_iter = colorize_nt_iter(nt_iter)
  if wide:
    display_tree_wide(tree_root, out, nt_iter)
  else:
    display_tree_narrow(tree_root, out, nt_iter)

def display_tree_narrow(tree_root, out, nt_iter, style=STYLE_UNICODE):
  """
  Display an ASCII tree from a tree object.
  """

  is_single_child = False
  for nt in nt_iter:
    if not is_single_child and nt.min_depth(2):
      for nt1 in nt.iter_parents(min_depth=2):
        if nt1.is_last_sib:
          out.write(style[0])
        else:
          out.write(style[1])
      if nt.is_last_sib:
        out.write(style[2])
      else:
        out.write(style[3])
    # May need quoting / escaping (already done if --color was used)
    out.write(nt.node.pvalue)
    if not nt.has_single_child:
      out.write('\n')
    else:
      if nt.node.value not in SPECIALS:
        out.write('/')
    is_single_child = nt.has_single_child

def iter_with_first_last(nt):
  """
  Yield elem, is_first, is_last, from an iterable.
  """

  el0 = None
  is_first = True
  for el in nt.node.children:
    if el0 is not None:
      yield NodeTraversal(el0, nt, is_first, False)
      is_first = False
    el0 = el
  if el0 is not None:
    yield NodeTraversal(el0, nt, is_first, True)

def display_tree_wide(tree_root, out, nt_iter, style=WIDE_STYLE_UNICODE):
  """
  Display an ASCII tree from a tree object.

  Less vertical space, more horizontal space, like pstree.
  """

  for nt in nt_iter:
    if nt.min_depth(2):
      if nt.is_first_sib:
        if nt.is_last_sib:
          out.write(style[1])
        else:
          out.write(style[2])
      else:
        first = True
        for nt1 in nt.iter_parents(min_depth=1):
          if not first:
            if nt1.is_last_sib:
              out.write(style[0])
            else:
              out.write(style[4])
          first = False
          out.write(' ' * len(nt1.node.value))
        if nt.is_last_sib:
          out.write(style[3])
        else:
          out.write(style[5])
    # May need quoting / escaping (already done if --color was used)
    out.write(nt.node.pvalue)
    if not nt.has_children:
      out.write('\n')

def line_iter_from_file(infile, zero_terminated=False):
  """
  Break a file into a line iterator.
  """

  if zero_terminated:
    # http://stromberg.dnsalias.org/~strombrg/readline0.html
    return readline0(infile)
  else:
    return (line.rstrip() for line in infile)

'''
git.git produces 2110 lines of arbo output.


Perf with git.git, a warm cache, ls per line:
real    0m18.375s
user    0m15.450s
sys     0m9.000s

Perf with git.git, a warm cache, ls in bulk by 40:
real    0m1.026s
user    0m0.690s
sys     0m0.270s

Bulk by 400:
real    0m0.558s
user    0m0.390s
sys     0m0.070s

'''

def split_line(path_str):
  if path_str[:2] == '//' and path_str[:3] != '///':
    # // special semantics (cf POSIX, last paragraph:)
    # http://www.opengroup.org/onlinepubs/009695399/basedefs/xbd_chap04.html#tag_04_11
    return [SLASHSLASH] + [el for el in path_str.split('/') if el]
  elif path_str[:1] == '/':
    return [SLASH] + [el for el in path_str.split('/') if el]
  else:
    # filter empty path components
    return [el for el in path_str.split('/') if el]

def tree_from_line_iter(line_iter, skip_dot, colorize):
  """
  Convert a path_iter-style iterator to a tree.

  itr is a path_iter-style iterator.
  postprocess takes a path, and prettifies it.
  """

  root = Node('ROOT')
  node_path0 = []
  for line in line_iter:
    str_path = split_line(line)
    parent = root
    node_path = []
    diverged = False

    for node0, str_comp in itertools.zip_longest(node_path0, str_path):
      if str_comp is None:
        break

      diverged = diverged or node0 is None or node0.value != str_comp
      if not diverged:
        node = node0
      else:
        node = Node(str_comp)
        parent.children.append(node)

      node_path.append(node)
      parent = node

    node_path0 = node_path
  if skip_dot and len(root.children) == 1 and root.children[0].value == '.':
    root = root.children[0]
  return root

def postprocess_path(nt_bulk):
  """
  Take a path, colorize and quote it.

  Assumes the path is to an existing file, rooted in the current directory.

  ls's colorisation logic is complicated, it has to handle stuff like
  LS_COLORS and that means parsing a lot of stat info.

  Delegating to ls is also hard, unless we change directories as often
  as necessary so that we don't have to edit output. Editing output
  is hard because colour escapes can be tricky.
  Calling ls is more conveniently done line by line so that our tree
  decorations don't get colored.
  Delegating to ls also buys us flexible escaping and quoting.

  This used to be done line by line with directory changes,
  until I bit the bullet and made it edit the ansi escapes in ls output.
  Custom escape codes for unusual terminals, which LS_COLORS
  might contain, aren't handled yet.
  Otherwise the output is exactly what ls gives us.
  """

  path_strs = [nt.path_str for nt in nt_bulk]

  # Acceptable quoting styles:
  # - mustn't keep newlines.
  # - mustn't keep \e (used in ansi color escapes).
  # c-maybe (preferred), c, escape.
  # c-maybe is lacking in jaunty due to an old gnulib
  # somewhere in buildd or source pkg.
  proc = subprocess.Popen(
      'ls -U -1d --color=always --quoting-style=escape --'.split() \
      + path_strs, stdout=subprocess.PIPE)

  nt_iter = iter(nt_bulk)
  for line in proc.stdout:
    line = line.decode('utf8')
    if line == END_LS:
      continue
    nt = next(nt_iter)
    node = nt.node

    #sys.stderr.write('%r\n' % line)
    groups = WITH_COLOR_RE.match(line).groups()
    #sys.stderr.write('%r\n' % (groups,))
    # color might be None
    color, last_component = groups
    node.color = color
    node.value = last_component

  if proc.wait():
    raise RuntimeError('Failed to postprocess paths')


def main():
  """
  Read from stdin, display to stdout.

  These two should be identical apart for unicode/terminal escaping,
  the switch to non-ascii tree style, and color subtleties
  find |LANG= sort |./arbo.py stdin --color
  tree -a --noreport

  With bash:
  diff -u <(tree -a --noreport) <(find |LANG= sort |./arbo.py)
  """

  locale.setlocale(locale.LC_ALL, '')
  sysencoding = locale.getpreferredencoding(False)
  reader_factory = codecs.getreader(sysencoding)

  parser = argparse.ArgumentParser()
  parser.add_argument('--wide', action='store_true', dest='wide',
      help='Use more horizontal space and less vertical space')

  # XXX http://bugs.python.org/issue9253
  sub = parser.add_subparsers(dest='source', default='stdin')

  sub_help = sub.add_parser('help',
      description='Print usage help')
  sub_help.add_argument('command', nargs='?')

  sub_stdin = sub.add_parser('stdin',
      description='Display paths listed from stdin (the default)')
  sub_stdin.set_defaults(cmd=None)
  sub_stdin.add_argument('-0',
      action='store_true', dest='zero_terminated',
      help='Input is zero-terminated')
  sub_stdin.add_argument('--color',
      action='store_true', dest='colorize',
      help='Input is local file names, which should be colorized')
  sub_stdin.add_argument('--skip-dot',
      action='store_true', dest='skip_dot',
      help='Input filenames are expected to all start with a dot; '
           'don\'t display the dot')

  sub_find = sub.add_parser('find',
      description='Display files below the current directory')
  sub_find.set_defaults(
    cmd=['find', '-print0', ],
    zero_terminated=True, colorize=True, skip_dot=True)

  sub_dpkg = sub.add_parser('dpkg',
      description='List a package\'s files')
  sub_dpkg.add_argument('package')
  sub_dpkg.set_defaults(
    cmd=['dpkg', '-L', '--', ],
    zero_terminated=False, colorize=True, skip_dot=False)

  # http://git.savannah.gnu.org/gitweb/?p=gnulib.git;a=blob;f=build-aux/vc-list-files;hb=HEAD
  sub_bzr = sub.add_parser('bzr',
      description='Display bzr-managed files')
  sub_bzr.set_defaults(
    cmd=['bzr', 'ls', '--recursive', '--versioned', '--null', ],
    zero_terminated=True, colorize=True, skip_dot=False)

  sub_cvs = sub.add_parser('cvs',
      description='Display cvs-managed files')
  sub_cvs.set_defaults(
    cmd=['cvsu', '--find', '--types=AFGM', ],
    zero_terminated=False, colorize=True, skip_dot=False)

  # This one is way too slow.
  # The only command to go online.
  sub_svn = sub.add_parser('svn',
      description='Display svn-managed files')
  sub_svn.set_defaults(
    cmd=['svn', 'list', '-R', ],
    zero_terminated=False, colorize=True, skip_dot=False)

  sub_git = sub.add_parser('git',
      description='Display git-managed files')
  sub_git.set_defaults(
    cmd=['git', 'ls-files', '-z', ],
    zero_terminated=True, colorize=True, skip_dot=False)

  sub_hg = sub.add_parser('hg',
      description='Display hg-managed files')
  sub_hg.set_defaults(
    cmd=['hg', 'locate', '--include', '.', '-0', ],
    zero_terminated=True, colorize=True, skip_dot=False)

  sub_darcs = sub.add_parser('darcs',
      description='Display darcs-managed files')
  sub_darcs.set_defaults(
    cmd=['darcs', 'show', 'files', '-0', ],
    zero_terminated=True, colorize=True, skip_dot=True)

  sub_fossil = sub.add_parser('fossil',
      description='Display fossil-managed files')
  sub_fossil.set_defaults(
    cmd=['fossil', 'ls', ],
    zero_terminated=False, colorize=True, skip_dot=False)

  args = parser.parse_args()
  src = args.source

  # So colours work
  chdir = None

  if src == 'help':
    # Not really a source, this subcommand just shows the help
    if args.command is None or args.command not in sub._name_parser_map:
      parser.print_help()
    else:
      sub._name_parser_map[args.command].print_help()
    return

  elif src == 'git':
    # A bit more complicated to support outside worktree operation.
    is_inside_work_tree = subprocess.check_output(
        ['git', 'rev-parse', '--is-inside-work-tree', ],
        ).rstrip() == b'true'
    if not is_inside_work_tree:
      is_bare_repository = subprocess.check_output(
          ['git', 'rev-parse', '--is-bare-repository', ],
          ).rstrip() == b'true'
      if is_bare_repository:
        colorize = False
      else:
        git_root = subprocess.check_output(
            ['git', 'rev-parse', '--show-cdup', ],
            ).rstrip()
        # Empty if at repo root; correctly bombs outside repo.
        if git_root:
          chdir = git_root
  # Unlike git, svn, cvs and bzr, the output of hg, darcs, and fossil
  # is rooted in the repo.
  elif src == 'hg':
    chdir = subprocess.check_output(['hg', 'root', ]).rstrip()
  elif src == 'darcs':
    chdir = subprocess.check_output(
        ['sh', '-c', 'darcs show repo |sed -n "s#^[[:space:]]*Root: ##p"', ],
        ).rstrip()
  elif src == 'fossil':
    chdir = subprocess.check_output(
        ['sh', '-c', 'fossil info |sed -n "s#^local-root:[[:space:]]*##p"', ],
        ).rstrip()
  elif src == 'dpkg':
    args.cmd.append(args.package)

  if args.cmd:
    fin_proc = subprocess.Popen(args.cmd, stdout=subprocess.PIPE)
    fin = reader_factory(fin_proc.stdout)
  else:
    fin = sys.stdin

  if chdir:
    # Do this *after* Popen has forked
    os.chdir(chdir)

  line_iter = line_iter_from_file(fin, zero_terminated=args.zero_terminated)
  # We can't directly convert iterators without building a tree,
  # because computing is_last_sib along the parent axis
  # requires seeking forward.
  tree = tree_from_line_iter(line_iter,
      skip_dot=args.skip_dot, colorize=args.colorize)
  display_tree(tree, sys.stdout, wide=args.wide, colorize=args.colorize)

  if args.cmd:
    returncode = fin_proc.wait()
    if returncode:
      raise subprocess.CalledProcessError(args.cmd, returncode)

if __name__ == '__main__':
  sys.exit(main())

"""
Ideas:
  mix two lists, one being a filter for the other.
  eg, git ls-files and the filesystem
  preconfigure:
    git ls-files -o --exclude-standard
    ack -f
    # more at http://git.savannah.gnu.org/gitweb/?p=gnulib.git;a=blob;f=build-aux/vc-list-files;hb=HEAD

"""

