#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A simple python dependency checker.

Scans given python modules and see their dependency. Usage:
  deps.py PYTHON_FILE(s)...
"""

import distutils.sysconfig as sysconfig
import importlib
import os
import sys


def GetDependencyList(path, base, exclude, include):
  """Gets dependency list of a given Python module.

  Args:
    path: A string for python module file (*.py).
    base: A list of base modules that should not be returned.
    exclude: A string of module path prefix to exclude.
    include: A string of module path prefix to include (overrides exclude).

  Returns:
    A list of strings for files of module dependency.
  """
  try:
    path = os.path.abspath(path)
    dir_path = os.path.dirname(path)
    basename = os.path.basename(path)
    if dir_path and (dir_path not in sys.path):
      sys.path.append(dir_path)
    target = importlib.import_module(basename.rpartition('.py')[0])
    new_names = [name for name in sys.modules if name not in base]
    new_modules = [sys.modules[name] for name in new_names if sys.modules[name]]
    new_modules.remove(target)
    dependency = []
    for module in new_modules:
      if '__file__' not in module.__dict__:
        # Assume this is a built-in module.
        continue
      module_path = module.__file__
      if (module_path.startswith(exclude) and
          not module_path.startswith(include)):
        continue
      dependency.append(module_path)
    # Unload new modules by deleting all references.
    for name in new_names:
      del sys.modules[name]
    return dependency
  except:
    print 'Failed checking %s.' % path
    raise


def main(argv):
  """Main entry point for command line invocation.

  Args:
    argv: list of files to check dependency.
  """
  base = sys.modules.copy()
  # Exclude Python Standard Library and include site packages.
  exclude = sysconfig.get_python_lib(standard_lib=True)
  include = sysconfig.get_python_lib(standard_lib=False)

  for path in argv:
    if not path.endswith('.py'):
      continue
    if path.endswith('_unittest.py'):
      continue
    print '--- %s ---' % os.path.basename(path)
    deps = GetDependencyList(path, base, exclude, include)
    print deps


if __name__ == '__main__':
  main(sys.argv[1:])
