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
  r'^(\033\[0m)?(\033\[[0-9]+;[0-9]+m)?([^\n\033]+)(\033\[0m)?\n(\033\[m)?$')
END_COLOR = '\033[0m'
END_LS = '\033[m'

# Ways to display a tree
STYLE_ASCII = ('    ', '|   ', '`-- ', '|-- ', )
STYLE_UNICODE = ('   ', '│  ', '└─ ', '├─ ', )

# How many paths in one ls call
BULK_LS_COUNT = 400


class Node(object):
  """
  A tree node.

  Children is an iterable.
  Value is a path element.
  """

  def __init__(self, value, pvalue, children=None):
    if children is None:
      children = []
    self.value = value
    self.pvalue = pvalue
    self.children = children

  def __repr__(self):
    if self.children == []:
      return 'Node(%r, %r)' % (self.value, self.pvalue)
    return 'Node(%r, %r, %r)' % (self.value, self.pvalue, self.children)

def traverse_tree(node, last_vector):
  """
  Traverse a tree in an order appropriate for graphic display.

  Traverse a tree in depth-first order, returning a
  (value, last_vector, has_single_child)
  iterator where value is the node value and last_vector a vector
  of booleans that represent which nodes in the parent chain are
  the last of their siblings. has_single_child is self-explanatory.

  last_vector is important for display, it tells where vertical lines end.
  """

  yield (node.pvalue, last_vector, len(node.children) == 1)
  prev_sibling = None
  last_vector.append(False)
  for sibling in node.children:
    if prev_sibling is not None:
      for e in traverse_tree(prev_sibling, last_vector):
        yield e
    prev_sibling = sibling
  if prev_sibling is not None:
    last_vector[-1] = True
    for e in traverse_tree(prev_sibling, last_vector):
      yield e
  last_vector.pop()

def traverse_tree_skip_root(root):
  """
  Tree traversal, skipping the root.

  Like traverse_tree, but you don't need to initialize last_vector
  and you skip the root.
  """

  for node in root.children:
    for e in traverse_tree(node, []):
      yield e

def display_tree(tree_root, out, style=STYLE_UNICODE):
  """
  Display an ASCII tree from a tree object.
  """

  is_single_child = False
  for (value, last_vector, has_single_child) in \
      traverse_tree_skip_root(tree_root):
    if bool(last_vector) and not is_single_child:
      for is_last in last_vector[:-1]:
        if is_last:
          out.write(style[0])
        else:
          out.write(style[1])
      if last_vector[-1]:
        out.write(style[2])
      else:
        out.write(style[3])
    # May need quoting / escaping (already done if --color was used)
    out.write(value)
    if not has_single_child:
      out.write('\n')
    else:
      if value not in SPECIALS:
        out.write('/')
    is_single_child = has_single_child

def line_iter_from_file(infile, zero_terminated=False):
  """
  Break a file into a line iterator.
  """

  if zero_terminated:
    # http://stromberg.dnsalias.org/~strombrg/readline0.html
    return readline0(infile)
  else:
    return (line.rstrip() for line in infile)

def path_iter_from_line_iter(itr, colorize=False):
  """
  Break a line iterator into one of sequences of path components.
  """

  if not colorize:
    for path_str in itr:
      yield split_line(path_str), ''
  else:
    while True:
      path_strs = list(itertools.islice(itr, BULK_LS_COUNT))
      if not path_strs:
        return
      for (path_str, color) in postprocess_path(path_strs):
        yield split_line(path_str), color

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

def tree_from_path_iter(itr):
  """
  Convert a path_iter-style iterator to a tree.

  itr is a path_iter-style iterator.
  postprocess takes a path, and prettifies it.
  """

  root = Node('ROOT', 'ROOT')
  node_path0 = []
  for (str_path, color) in itr:
    parent = root
    node_path = []
    diverged = False

    for node0, str_comp in itertools.zip_longest(node_path0, str_path):
      if str_comp is None:
        break

      diverged |= node0 is None or node0.value != str_comp
      if not diverged:
        node = node0
      else:
        if color:
          pvalue = color + str_comp + END_COLOR
        else:
          pvalue = str_comp
        node = Node(str_comp, pvalue)
        parent.children.append(node)

      node_path.append(node)
      parent = node

    node_path0 = node_path
  return root

def postprocess_path(path_strs):
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
  Escape changes, which LS_COLORS can also contain, aren't handled yet.
  """

  # Acceptable quoting styles:
  # - mustn't keep newlines.
  # - mustn't keep \e (used in ansi color escapes).
  # c-maybe (preferred), c, escape.
  # c-maybe is lacking in jaunty due to an old gnulib
  # somewhere in buildd or source pkg.
  proc = subprocess.Popen(
      'ls -1d --color=always --quoting-style=escape --'.split() \
      + path_strs, stdout=subprocess.PIPE)

  for line in proc.stdout:
    line = line.decode('utf8')
    if line == END_LS:
      continue

    #sys.stderr.write('%r\n' % line)
    groups = WITH_COLOR_RE.match(line).groups()
    #sys.stderr.write('%r\n' % (groups,))
    # r0, r1, r2: all reset sequences
    r0, color, path_str, r1, r2 = groups
    yield path_str, color

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
  # XXX http://bugs.python.org/issue9253
  sub = parser.add_subparsers(dest='source', default='stdin')

  sub_stdin = sub.add_parser('stdin',
      description='Display paths listed from stdin (the default)')
  sub_stdin.set_defaults(cmd=None)
  sub_stdin.add_argument('-0',
      action='store_true', dest='zero_terminated',
      help='Input is zero-terminated')
  sub_stdin.add_argument('--color',
      action='store_true', dest='colorize',
      help='Input is local file names, which should be colorized')

  sub_find = sub.add_parser('find',
      description='Display files below the current directory')
  sub_find.set_defaults(
    cmd=['find', '-print0', ],
    zero_terminated=True, colorize=True)

  sub_dpkg = sub.add_parser('dpkg',
      description='List a package\'s files')
  sub_dpkg.add_argument('package')
  sub_dpkg.set_defaults(
    cmd=['dpkg', '-L', '--', ],
    zero_terminated=False, colorize=True)

  # http://git.savannah.gnu.org/gitweb/?p=gnulib.git;a=blob;f=build-aux/vc-list-files;hb=HEAD
  sub_bzr = sub.add_parser('bzr',
      description='Display bzr-managed files')
  sub_bzr.set_defaults(
    cmd=['bzr', 'ls', '--recursive', '--versioned', '--null', ],
    zero_terminated=True, colorize=True)

  sub_cvs = sub.add_parser('cvs',
      description='Display cvs-managed files')
  sub_cvs.set_defaults(
    cmd=['cvsu', '--find', '--types=AFGM', ],
    zero_terminated=False, colorize=True)

  sub_svn = sub.add_parser('svn',
      description='Display svn-managed files')
  sub_svn.set_defaults(
    cmd=['svn', 'list', '-R', ],
    zero_terminated=False, colorize=True)

  sub_git = sub.add_parser('git',
      description='Display git-managed files')
  sub_git.set_defaults(
    cmd=['git', 'ls-files', '-z', ],
    zero_terminated=True, colorize=True)

  sub_hg = sub.add_parser('hg',
      description='Display hg-managed files')
  sub_hg.set_defaults(
    cmd=['hg', 'locate', '--include', '.', '-0', ],
    zero_terminated=True, colorize=True)

  sub_darcs = sub.add_parser('darcs',
      description='Display darcs-managed files')
  sub_darcs.set_defaults(
    cmd=['darcs', 'show', 'files', '-0', ],
    zero_terminated=True, colorize=True)

  sub_fossil = sub.add_parser('fossil',
      description='Display fossil-managed files')
  sub_fossil.set_defaults(
    cmd=['fossil', 'ls', ],
    zero_terminated=False, colorize=True)

  args = parser.parse_args()
  src = args.source

  # So colours work
  chdir = None

  if src == 'git':
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
  path_iter = path_iter_from_line_iter(line_iter, colorize=args.colorize)
  # We can't directly convert iterators without building a tree,
  # because computing last_vector requires seeking forward.
  tree = tree_from_path_iter(path_iter)
  display_tree(tree, sys.stdout)

  if args.cmd:
    returncode = fin_proc.wait()
    if returncode:
      raise subprocess.CalledProcessError(args.cmd, returncode)

if __name__ == '__main__':
  main()

"""
Ideas:
  compact tree (a la pstree)
  mix two lists, one being a filter for the other.
  eg, git ls-files and the filesystem
  preconfigure:
    git ls-files
    git ls-files -o --exclude-standard
    hg locate
    bzr ls
    ack -f
    xargs -0a <(find -print0) ls -d --color=force
    # more at http://git.savannah.gnu.org/gitweb/?p=gnulib.git;a=blob;f=build-aux/vc-list-files;hb=HEAD

"""

