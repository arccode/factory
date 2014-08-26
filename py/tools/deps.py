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
import re
import sys

import yaml


# Constants for config file.
CONFIG_GROUPS = r'groups'
CONFIG_RULES = r'rules'
CONFIG_GROUP_PATTERN = re.compile(r'^<([^<>].*)>$')
CONFIG_WILD_IMPORTS = r'*'


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
    dir_path = os.path.dirname(path)
    basename = os.path.basename(path)
    sys.path.insert(0, dir_path)
    target = importlib.import_module(basename.rpartition('.py')[0])
    sys.path.pop(0)
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


def CheckDependencyList(module, depends, rules, package_top, standard_lib,
                        site_packages):
  """Checks if given module and dependency complies to the rules.

  Args:
    module: A string for full path of reference module.
    depends: A list of strings for files imported by module.
    rules: A dictionary of {package: imports} that package is only allowed to
           import from the "imports" list.
    package_top: A string of path to the top level of package.
    standard_lib: A string for Python standard library path.
    site_packages: A string for Python site packages path.

  Returns:
    A list of strings for modules that should not be imported.
  """
  def GetPackage(py_path, package_top):
    """Converts a Python file path into Python package name."""
    if py_path.startswith(site_packages):
      py_path = py_path.replace(site_packages + os.path.sep, '', 1)
      py_path = (os.path.dirname(py_path) if os.path.dirname(py_path) else
                 os.path.splitext(py_path)[0])
    elif py_path.startswith(standard_lib):
      py_path = py_path.replace(standard_lib + os.path.sep, '', 1)
    elif py_path.startswith(package_top):
      # Note py_path may start as factory/py or factory/py_pkg/cros/factory.
      py_path = py_path.replace(package_top, 'cros/factory', 1).replace(
          'factory_pkg/cros/', '', 1)
    py_path = (os.path.dirname(py_path) if os.path.dirname(py_path) else
               os.path.splitext(py_path)[0])
    return py_path.replace(os.path.sep, '.').strip('.')

  def FindRule(package, rules):
    """Finds the best rule that matches given package."""
    while '.' in package:
      if package in rules:
        return rules[package]
      package = package.rpartition('.')[0]
    raise Exception('Unknown package: %s' % package)

  result = set()
  package = GetPackage(module, package_top)
  rule = FindRule(package, rules)
  if CONFIG_WILD_IMPORTS in rule:
    return list(result)

  # Match modules
  for path in depends:
    if path.endswith('/factory_common.pyc'):
      # factory_common is symlink everywhere and hard to check.
      continue
    package = GetPackage(path, package_top)
    if package == 'cros' and path.endswith('__init__.pyc'):
      # Allow only this implicitly loaded file in 'cros' package.
      continue
    if package not in rule:
      result.add('%s (%s)' % (package, path))
  return list(result)


def LoadConfiguration(path):
  """Loads dependency rules from a given (YAML) configuration file.

  Args:
    path: A string of file path to a YAML config file.

  Returns:
    A dictionary of {package: imports} describing "'package' can only import
    from 'imports'".
  """
  config = yaml.load(open(path))
  if (CONFIG_GROUPS not in config) or (CONFIG_RULES not in config):
    raise ValueError('Syntax error in %s' % path)
  groups = config[CONFIG_GROUPS]
  rules = {}
  for key, value in config[CONFIG_RULES].items():
    # Expand value into imports
    imports = []
    for package in value:
      if re.match(CONFIG_GROUP_PATTERN, package):
        imports += groups[re.findall(CONFIG_GROUP_PATTERN, package)[0]]
      else:
        imports.append(package)
    if re.match(CONFIG_GROUP_PATTERN, key):
      # Duplicate multiple rules
      for module in groups[re.findall(CONFIG_GROUP_PATTERN, key)[0]]:
        rules[module] = imports
    else:
      rules[key] = imports
  return rules


def main(argv):
  """Main entry point for command line invocation.

  Args:
    argv: list of files to check dependency.
  """
  base = sys.modules.copy()
  standard_lib = sysconfig.get_python_lib(standard_lib=True)
  site_packages = sysconfig.get_python_lib(standard_lib=False)
  exit_value = 0

  # Configuration file should be located in same folder.
  # "cros.factory" should be mapped to parent folder of this program.
  rules = LoadConfiguration(os.path.splitext(os.path.realpath(__file__))[0] +
                            '.conf')
  package_top = os.path.abspath(os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      '..'))

  for path in argv:
    if not path.endswith('.py'):
      continue
    if path.endswith('_unittest.py'):
      continue
    print '--- %s ---' % os.path.basename(path)
    # For symlink python files, we want to keep its path directory so abspath
    # is better than realpath.
    path = os.path.abspath(path)
    # Exclude Python Standard Library and include site packages.
    deps = GetDependencyList(path, base, standard_lib, site_packages)
    bad_imports = CheckDependencyList(path, deps, rules, package_top,
                                      standard_lib, site_packages)
    if bad_imports:
      print '\n'.join(bad_imports)
      exit_value = 1
  sys.exit(exit_value)


if __name__ == '__main__':
  main(sys.argv[1:])
