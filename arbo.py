#!/usr/bin/python3 -S
# vim: set fileencoding=utf-8 sw=2 ts=2 et :
from __future__ import absolute_import

import codecs
import locale
import optparse
import os
import subprocess
import sys
from arbo_readline0 import readline0

SLASH = object()
SLASHSLASH = object()
CWD = object()
SPECIALS = (SLASH, SLASHSLASH, CWD)

try:
  from itertools import izip_longest
except ImportError:
  # Not a perfect reimpl, but sufficient
  def izip_longest(*iterators):
    fillvalue = None
    iterators = tuple(iter(el) for el in iterators)
    okset = set(range(len(iterators)))
    def it_next(pos, it):
      try:
        return next(it)
      except StopIteration:
        okset.discard(pos)
        return fillvalue
    while True:
      r = tuple(it_next(pos, it) for (pos, it) in enumerate(iterators))
      if not okset: #empty
        raise StopIteration
      yield r


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
    if node.value == CWD:
      for e in traverse_tree_skip_root(node):
        yield e
    else:
      for e in traverse_tree(node, []):
        yield e

STYLE_ASCII = ('    ', '|   ', '`-- ', '|-- ', )
STYLE_UNICODE = ('   ', '│  ', '└─ ', '├─ ', )

def display_tree(tree_root, out, style=STYLE_UNICODE):
  """
  Display an ASCII tree from a tree object.
  """

  is_single_child = False
  for (value, last_vector, has_single_child) in \
      traverse_tree_skip_root(tree_root):
    if last_vector and not is_single_child: #tests for emptiness
      for is_last in last_vector[:-1]:
        if is_last:
          out.write(style[0])
        else:
          out.write(style[1])
      if last_vector[-1]:
        out.write(style[2])
      else:
        out.write(style[3])
    if value == SLASH:
      out.write('/')
      if not has_single_child:
        out.write('\n')
    elif value == SLASHSLASH:
      out.write('//')
      if not has_single_child:
        out.write('\n')
    elif value == CWD:
      if not has_single_child:
        out.write('.\n')
    else:
      # May need quoting / escaping
      out.write(value)
      if has_single_child:
        out.write('/')
      else:
        out.write('\n')
    is_single_child = has_single_child

def path_iter_from_file(infile, sep='/', zero_terminated=False):
  """
  Break a file into an iterator of sequences of path components.
  """

  if zero_terminated:
    # http://stromberg.dnsalias.org/~strombrg/readline0.html
    itr = readline0(infile)
  else:
    itr = (line.rstrip() for line in infile)
  for path_str in itr:
    if path_str[:2] == '//' and path_str[:3] != '///':
      # // special semantics (cf POSIX)
      yield [SLASHSLASH] + [el for el in path_str.split(sep) if el]
    elif path_str[:1] == '/':
      yield [SLASH] + [el for el in path_str.split(sep) if el]
    else:
      # filters empty path components
      if False:
        yield [CWD] + [el for el in path_str.split(sep) if el]
      else:
        # If we don't generate CWD, no need to handle it anywhere else.
        yield [el for el in path_str.split(sep) if el]

def tree_from_path_iter(itr, postprocess=None):
  """
  Convert a path_iter-style iterator to a tree.

  itr is a path_iter-style iterator.
  postprocess takes a path, and prettifies it.
  """

  root = Node('ROOT', 'ROOT')
  node_path0 = []
  for str_path in itr:
    parent = root
    node_path = []
    diverged = False
    for node0, str_comp in izip_longest(node_path0, str_path):
      if str_comp is None:
        break
      diverged |= node0 is None or node0.value != str_comp
      if not diverged:
        node = node0
      else:
        if postprocess:
          pvalue = postprocess(str_path[:len(node_path)], str_comp)
        else:
          pvalue = str_comp
        node = Node(str_comp, pvalue)
        parent.children.append(node)
      node_path.append(node)
      parent = node
    node_path0 = node_path
  return root

def postprocess_color_quote(parent_path, name):
  """
  Take a path, colorize the last path element (or the full path, for now).

  Assumes the path is to an existing file, rooted in the current directory.
  ls's colorisation logic is complicated, it has to handle stuff like
  LS_COLORS and that means parsing a lot of stat info.

  Delegating to ls is also hard, unless we change directories as often
  as necessary so that we don't have to edit output. Editing output would
  be hard because colours could be complicated to parse.
  ls output must be gotten line by line so that our tree decorations
  don't get colored.
  delegating to ls also buys us flexible escaping and quoting.
  """

  if name in SPECIALS:
    return name
  if parent_path:
    if parent_path[0] == CWD:
      parent_path[0] = '.'
    elif parent_path[0] == SLASH:
      if len(parent_path) > 1:
        parent_path[0] = ''
      else:
        parent_path[0] = '/'
    elif parent_path[0] == SLASHSLASH:
      if len(parent_path) > 1:
        parent_path[0] = '/'
      else:
        parent_path[0] = '//'
    parent_path_str = '/'.join(parent_path)
  else:
    parent_path_str = None
  # Acceptable quoting styles: those that don't keep newlines.
  # c-maybe (preferred), c, escape.
  # c-maybe is lacking in jaunty due to old gnulib
  # somewhere in buildd or source pkg.
  try:
    outd = subprocess.check_output([
        'ls', '-1d', '--color=always', '--quoting-style=escape', '--',
        name, ], cwd=parent_path_str)
  except subprocess.CalledProcessError:
    raise RuntimeError('Failed to postprocess path', parent_path_str, name)
  outd = outd.decode('utf8')
  newline_pos = outd.find('\n')
  return outd[:newline_pos] # Strip newline and colour reset.

def traverse_tree_from_path_iter_XXX(itr):
  """
  Convert a path_iter-style iterator to a traverse_tree iterator.

  We can't directly convert iterators without building a tree,
  because computing last_vector requires seeking forward.
  """

  return traverse_tree_skip_root(tree_from_path_iter(itr))

def main():
  """
  Read from stdin, display to stdout.

  These two should be identical apart for unicode/terminal escaping,
  the switch to non-ascii tree style, and color
  find |LANG= sort |./arbo.py
  tree -a --noreport

  With bash:
  diff -u <(tree -a --noreport) <(find |LANG= sort |./arbo.py)
  """

  locale.setlocale(locale.LC_ALL, '')
  sysencoding = locale.getpreferredencoding(False)
  reader_factory = codecs.getreader(sysencoding)

  parser = optparse.OptionParser()
  parser.set_defaults(
      source='stdin',
      zero_terminated=False,
      colorize=False,
      )
  # Maybe argparse-style subcommands would fit better.
  parser.add_option('--stdin',
      action='store_const', dest='source', const='stdin',
      help='Display paths listed from stdin (the default)')
  parser.add_option('--bzr',
      action='store_const', dest='source', const='bzr',
      help='Display bzr-managed files')
  parser.add_option('--cvs',
      action='store_const', dest='source', const='cvs',
      help='Display cvs-managed files')
  parser.add_option('--darcs',
      action='store_const', dest='source', const='darcs',
      help='Display darcs-managed files')
  parser.add_option('--fossil',
      action='store_const', dest='source', const='fossil',
      help='Display fossil-managed files')
  parser.add_option('--git',
      action='store_const', dest='source', const='git',
      help='Display git-managed files')
  parser.add_option('--hg',
      action='store_const', dest='source', const='hg',
      help='Display hg-managed files')
  parser.add_option('--svn',
      action='store_const', dest='source', const='svn',
      help='Display svn-managed files')
  parser.add_option('--find',
      action='store_const', dest='source', const='find',
      help='Display files below the current directory')

  parser.add_option('-0',
      action='store_true', dest='zero_terminated',
      help='Input is zero-terminated')
  parser.add_option('--color',
      action='store_true', dest='colorize',
      help='Input is local file names, which should be colorized')

  (options, args) = parser.parse_args()
  src = options.source

  # So colours work
  chdir = None

  if src == 'stdin':
    cmd = None
    fin = sys.stdin
    zero_terminated = options.zero_terminated
    colorize = options.colorize
  elif src == 'bzr':
    # http://git.savannah.gnu.org/gitweb/?p=gnulib.git;a=blob;f=build-aux/vc-list-files;hb=HEAD
    cmd = ['bzr', 'ls', '--recursive', '--versioned', '--null', ]
    zero_terminated = True
    colorize = True
  elif src == 'cvs':
    cmd = ['cvsu', '--find', '--types=AFGM', ]
    zero_terminated = False
    colorize = True
  elif src == 'svn':
    cmd = ['svn', 'list', '-R', ]
    zero_terminated = False
    colorize = True
  elif src == 'git':
    # A bit more complicated to support outside worktree operation.
    cmd = ['git', 'ls-files', '-z', ]
    zero_terminated = True
    colorize = True
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
  elif src == 'hg':
    cmd = ['hg', 'locate', '--include', '.', '-0', ]
    zero_terminated = True
    colorize = True
    # Unlike git, svn, cvs and bzr, hg locate output is
    # rooted in the repo not the cwd.
    chdir = subprocess.check_output(['hg', 'root', ]).rstrip()
  elif src == 'darcs':
    cmd = ['darcs', 'show', 'files', '-0', ]
    zero_terminated = True
    colorize = True
    # Unlike git, svn, cvs and bzr, this is rooted in the repo not the cwd.
    chdir = subprocess.check_output(
        ['sh', '-c', 'darcs show repo |sed -n "s#^[[:space:]]*Root: ##p"', ],
        ).rstrip()
  elif src == 'fossil':
    cmd = ['fossil', 'ls', ]
    zero_terminated = False
    colorize = True
    # Unlike git, svn, cvs and bzr, this is rooted in the repo not the cwd.
    chdir = subprocess.check_output(
        ['sh', '-c', 'fossil info |sed -n "s#^local-root:[[:space:]]*##p"', ],
        ).rstrip()
  elif src == 'find':
    cmd = ['find', '-print0', ]
    zero_terminated = True
    colorize = True
  else:
    raise NotImplementedError

  if cmd:
    fin_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    fin = reader_factory(fin_proc.stdout)

  if chdir:
    os.chdir(chdir)

  if colorize:
    postprocess = postprocess_color_quote
  else:
    postprocess = None
  display_tree(
      tree_from_path_iter(
        path_iter_from_file(fin, zero_terminated=zero_terminated),
        postprocess=postprocess),
      sys.stdout)
  if cmd:
    returncode = fin_proc.wait()
    if returncode:
      raise subprocess.CalledProcessError(cmd, returncode)

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

