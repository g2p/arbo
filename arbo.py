#!/usr/bin/python -S
# vim: set fileencoding=utf-8 sw=2 ts=2 et :
from __future__ import absolute_import

import subprocess

try:
  from itertools import izip_longest
except ImportError:
  # Not a perfect reimpl, but sufficient
  def izip_longest(*iterators):
    fillvalue = None
    iterators = tuple(iter(el) for el in iterators)
    okset = set(range(len(iterators)))
    def next(pos, it):
      try:
        return it.next()
      except StopIteration:
        okset.discard(pos)
        return fillvalue
    while True:
      r = tuple(next(pos, it) for (pos, it) in enumerate(iterators))
      if not okset: #empty
        raise StopIteration
      yield r


class Node(object):
  def __init__(self, value, children=None):
    if children is None:
      children = []
    self.value = value
    self.children = children

  def __repr__(self):
    if self.children == []:
      return 'Node(%r)' % self.value
    return 'Node(%r, %r)' % (self.value, self.children)

def traverse_tree(node, last_vector):
  """
  Traverse a tree in an order appropriate for graphic display.

  Traverse a tree in depth-first order, returning a (value, last_vector)
  iterator where value is the node value and last_vector a vector
  of booleans that represent which nodes in the parent chain are
  the last of their siblings.

  last_vector is important for display, it tells where vertical lines end.
  """

  yield (node.value, last_vector)
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

STYLE_ASCII = ('    ', '|   ', '`-- ', '|-- ', )
STYLE_UNICODE = ('   ', '│  ', '└─ ', '├─ ', )

def display_tree(itr, out, style=STYLE_UNICODE):
  """
  Display an ASCII tree from a traverse_tree-style iterator.
  """

  for (value, last_vector) in itr:
    if last_vector: #tests for emptiness
      for is_last in last_vector[:-1]:
        if is_last:
          out.write(style[0])
        else:
          out.write(style[1])
      if last_vector[-1]:
        out.write(style[2])
      else:
        out.write(style[3])
    # May need quoting / escaping
    out.write(value)
    out.write('\n')

def path_iter_from_file(infile, sep='/', zero_terminated=False):
  """
  Break a file into an iterator of sequences of path components.
  """

  if zero_terminated:
    # http://stromberg.dnsalias.org/~strombrg/readline0.html
    itr = NotImplemented
    raise NotImplementedError
  else:
    itr = (line.rstrip() for line in infile)
  for path_str in itr:
    # filters empty path components
    yield [el for el in path_str.split(sep) if el]

def tree_from_path_iter(itr):
  """
  Convert a path_iter-style iterator to a tree.
  """

  root = Node('ROOT')
  node_path0 = []
  for str_path in itr:
    parent = root
    node_path = []
    diverged = False
    for node0, str_comp in izip_longest(node_path0, str_path):
      if str_comp is None:
        break
      diverged = diverged or \
          node0 is None or node0.value != str_comp
      if not diverged:
        node = node0
      else:
        node = Node(str_comp)
        parent.children.append(node)
      node_path.append(node)
      parent = node
    node_path0 = node_path
  return root

def filecolors(itr):
  """
  Take a path, colorize the last path element.

  Assumes they are to existing files, rooted in the current directory.
  ls's colorisation logic is complicated, it has to handle stuff like
  LS_COLORS and that means parsing a lot of stat info.

  Delegating to ls is also hard, unless we change directories as often
  as necessary so that we don't have to edit output. Editing output would
  be hard because colours could be complicated to parse.
  ls output must be gotten line by line so that our tree decorations
  don't get colored.
  delegating to ls also buys us flexible escaping and quoting.
  """

  for path in itr:
    yield path

def traverse_tree_from_path_iter(itr):
  """
  Convert a path_iter-style iterator to a traverse_tree iterator.

  We can't directly convert iterators without building a tree,
  because computing last_vector requires seeking forward.
  """

  return traverse_tree_skip_root(tree_from_path_iter(itr))

def postprocess_zero_flist_file(fl):
  """
  Post-process a file listing zero-terminated, local file names.

  Adds color and escaping atm.
  """

  if True:
    return subprocess.Popen(['/usr/bin/xargs', '-0',
      '-n1', ],
      stdin=fl, stdout=subprocess.PIPE).stdout
  else:
    # Buggy: would colorize the complete path
    # and compromise tree building.
    return subprocess.Popen(['/usr/bin/xargs', '-0', #'-n1',
      'ls', '-1d', '--color=always', '--quoting-style=c-maybe', ],
      stdin=fl, stdout=subprocess.PIPE).stdout

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

  from optparse import OptionParser
  import sys

  parser = OptionParser()
  parser.set_defaults(source='stdin')
  # Maybe argparse-style subcommands would fit better.
  parser.add_option('--stdin',
      action='store_const', dest='source', const='stdin',
      help='Display paths listed from stdin')
  parser.add_option('--bzr',
      action='store_const', dest='source', const='bzr',
      help='Display bzr-managed files')
  parser.add_option('--git',
      action='store_const', dest='source', const='git',
      help='Display git-managed files')
  parser.add_option('--svn',
      action='store_const', dest='source', const='svn',
      help='Display svn-managed files')
  parser.add_option('--hg',
      action='store_const', dest='source', const='hg',
      help='Display hg-managed files')

  (options, args) = parser.parse_args()
  src = options.source

  if src == 'stdin':
    fin = sys.stdin
  elif src == 'bzr':
    # http://git.savannah.gnu.org/gitweb/?p=gnulib.git;a=blob;f=build-aux/vc-list-files;hb=HEAD
    fin = postprocess_zero_flist_file(subprocess.Popen(
      ['bzr', 'ls', '--versioned', '--null', ],
      stdout=subprocess.PIPE).stdout)
  elif src == 'git':
    fin = postprocess_zero_flist_file(subprocess.Popen(
      ['git', 'ls-files', '-z', ],
      stdout=subprocess.PIPE).stdout)
  elif src == 'svn':
    fin = postprocess_zero_flist_file(subprocess.Popen(
      ['svn', 'list', '-R', ],
      stdout=subprocess.PIPE).stdout)
  elif src == 'hg':
    # Unlike git, svn and bzr, this is rooted in the repository not the cwd.
    fin = postprocess_zero_flist_file(subprocess.Popen(
      ['hg', 'locate', '--include', '.', '-0', ],
      stdout=subprocess.PIPE).stdout)
  else:
    raise NotImplementedError

  display_tree(
      traverse_tree_from_path_iter(path_iter_from_file(fin)),
      sys.stdout)

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

