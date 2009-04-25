#!/usr/bin/python
# vim: set fileencoding=utf-8 sw=2 ts=2 et :
from __future__ import absolute_import

import itertools

class Node(object):
  def __init__(val, children=[]):
    self.val = val
    self.children = children

def traverse_tree(node, last_vector=[]):
  """
  Traverse a tree in an order appropriate for graphic display.

  Traverse a tree in breadth-first order, returning a (value, last_vector)
  iterator where value is the node value and last_vector a vector
  of booleans that represent which nodes in the parent chain are
  the last of their siblings.
  """

  yield (node.val, last_vector)
  prev_sibling = None
  last_vector.append(False)
  for sibling in node.children:
    if prev_sibling is not None:
      traverse_tree(prev_sibling, last_vector)
    prev_sibling = sibling
  if prev_sibling is not None:
    last_vector[-1] = True
    traverse_tree(prev_sibling, last_vector)
  last_vector.pop()

def display_tree(itr, out):
  """
  Display an ASCII tree from a traverse_tree-style iterator.
  """

  for (val, last_vector) in itr:
    for is_last in last_vector[:-1]:
      if is_last:
        out.write('   ')
      else:
        out.write('|  ')
    if last_vector[-1]:
      out.write('`--')
    else:
      out.write('|--')
    # May need quoting / escaping
    out.write(val)
    out.write('\n')

def path_iter_from_file(infile, sep='/', zero_terminated=False):
  if zero_terminated:
    raise NotImplementedError
  else:
    def itr():
      for line in infile:
        yield line.rstrip()
    itr = itr()
  for path_str in itr:
    yield path_str.split(sep)

def traverse_tree_from_path_iter(itr):
  """
  Convert a path_iter-style iterator to a traverse_tree-style iterator.
  """

  path0 = []
  path1 = []
  for path2 in itr:
    last_vector = []
    for comp0, comp1, comp2 in itertools.izip_longest(path0, path1, path2):
      if comp1 is None:
        break
      last_vector.append(comp1 != comp2)
      if comp0 != comp1:
        yield (comp1, last_vector)
    path0 = path1
    path1 = path2

def main():
  """
  Read from stdin, display to stdout.

  Compare these two:
  find |LANG= sort |./arbo.py
  tree -a
  """

  import sys
  display_tree(traverse_tree_from_path_iter(path_iter_from_file(sys.stdin)), sys.stdout)

if __name__ == '__main__':
  main()

