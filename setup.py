#!/usr/bin/env python

from distutils.core import setup

setup(name='arbo',
      version='0.1',
      author='Gabriel de Perthuis',
      author_email='g2p.code@gmail.com',
      description='Display a tree from a list of paths',
      license='http://www.gnu.org/licenses/gpl-2.0.html',
      long_description='Display a tree from a list of paths.\n'
        +'You can pipe data, or use vcs switches to display\n'
        +'all version-controlled files.\n',
      py_modules=[
           'arbo',
           ],
     )

