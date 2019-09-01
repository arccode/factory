#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A simple python dependency checker.

Scans given python modules and see their dependency. Usage:
  deps.py PYTHON_FILE(s)...
"""

from __future__ import print_function

import argparse
import ast
from distutils import sysconfig
import functools
import imp
import json
import multiprocessing
import os
import re
import subprocess
import sys

import yaml


# Constants for config file.
CONFIG_GROUPS = r'groups'
CONFIG_RULES = r'rules'
CONFIG_GROUP_PATTERN = re.compile(r'^<([^<>].*)>$')


# known import files that would manipulate sys.path.
# TODO(pihsun): Move this to the rule file.
PATH_MANIPULATE_IMPORTS = ['factory_common', 'instalog_common']

FACTORY_DIR = os.path.abspath(os.path.join(__file__, '..', '..', '..'))
PY_BASE_DIR = os.path.join(FACTORY_DIR, 'py')
PY_PKG_BASE_DIR = os.path.join(FACTORY_DIR, 'py_pkg', 'cros', 'factory')

STANDARD_LIB_DIR = sysconfig.get_python_lib(standard_lib=True) + '/'
SITE_PACKAGES_DIR = sysconfig.get_python_lib(standard_lib=False) + '/'


class ImportCollector(ast.NodeVisitor):
  """An ast.NodeVisitor that would collect all import statements in a file.

  To support conditional dependency, the imports in a try-catch block with
  ImportError catched would not be collected.
  """
  def __init__(self):
    self.import_list = []
    self.try_import_block_count = 0

  def visit_Import(self, node):
    """Visiting a 'import xxx.yyy' statement"""
    if self.try_import_block_count:
      return
    for alias in node.names:
      self.import_list.append({
          'module': alias.name,
          'level': 0,
          'import': None
      })

  def visit_ImportFrom(self, node):
    """Visiting a 'from xxx.yyy import zzz' statement"""
    if self.try_import_block_count:
      return
    for alias in node.names:
      self.import_list.append({
          'module': node.module or '',
          'level': node.level,
          'import': alias.name
      })

  def visit_TryExcept(self, node):
    if any(
        isinstance(x.type, ast.Name) and x.type.id == 'ImportError'
        for x in node.handlers):
      # We're in a try: ...; except ImportError: ... block, assume that this is
      # a conditional import, and don't add things inside to import list.
      self.try_import_block_count += 1
      self.generic_visit(node)
      self.try_import_block_count -= 1
    else:
      self.generic_visit(node)


def ReconstructSourceImport(item):
  """Reconstruct the original import line from values in ImportCollector.

  This is used to output human-friendly error message.
  """
  if item['import'] is None:
    return "import %s" % item['module']
  else:
    module = ''.join(['.'] * item['level'])
    module += item['module'] or ''
    return "from %s import %s" % (module, item['import'])


def GuessModule(filename):
  """Guess the module name from Python file name."""
  for base in [PY_BASE_DIR, PY_PKG_BASE_DIR]:
    if filename.startswith(base + '/'):
      relpath = filename[len(base) + 1:]
      subpaths = os.path.splitext(relpath)[0].split('/')
      if subpaths[-1] == '__init__':
        subpaths.pop()
      return 'cros.factory.' + '.'.join(subpaths)
  return None


def FindModule(name, paths):
  """Wrapper for imp.find_module, that returns (pathname, import_type)."""
  old_sys_path = list(sys.path)
  sys.path = paths
  try:
    # We need to modify sys.path instead of passing paths to argument of
    # find_module, since otherwise the builtin modules won't be found.
    fp, pathname, description = imp.find_module(name)
    if fp is not None:
      fp.close()
    return pathname, description[2]
  finally:
    sys.path = old_sys_path


def GuessIsBuiltin(module):
  """Guess if a module is builtin module for Python.

  A module is a builtin module for Python if either it's import type is
  imp.C_BUILTIN, or it's module path is inside standard library directory, and
  not inside site packages directory.
  """
  top_module = module.split('.')[0]
  try:
    path, module_type = FindModule(top_module, sys.path)
    if ((path.startswith(STANDARD_LIB_DIR) and
         not path.startswith(SITE_PACKAGES_DIR)) or
        module_type == imp.C_BUILTIN):
      return True
    return False
  except Exception:
    return False


def GetSysPathInDir(file_dir, additional_script=''):
  """Opens a subprocess to get the sys.path in a directory.

  If additional_script is given, it'll be run inside the subprocess.
  """
  return json.loads(
      subprocess.check_output(
          [
              'python2', '-c', (
                  'import sys\n'
                  'import os\n'
                  'import json\n'
                  '%s\n'
                  'print json.dumps([os.path.abspath(p) for p in sys.path])') %
              additional_script
          ],
          cwd=file_dir))


def GetImportList(filename, module_name):
  """Get a list of imported modules of the file."""
  file_dir = os.path.dirname(filename)
  current_sys_path = GetSysPathInDir(file_dir)
  import_list = []

  with open(filename, 'r') as fin:
    source = fin.read()

  root = ast.parse(source, filename)
  collector = ImportCollector()
  collector.visit(root)

  for item in collector.import_list:
    module = item['module']
    module_subpaths = module.split('.')
    import_item = item['import']

    if import_item is None:
      # import xxx.yyy

      # Although import a.b.c brings a, a.b, a.b.c into namespace, we assume
      # that the code meant to only depends on a.b.c.
      import_list.append(module)

      # import items in PATH_MANIPULATE_IMPORTS would change sys.path.
      if module in PATH_MANIPULATE_IMPORTS:
        current_sys_path = GetSysPathInDir(
            file_dir, 'sys.path = %r\nimport %s' % (current_sys_path, module))
    else:
      # from x.y.z import foo
      # Try to import x.y.z to see if foo is a method or a module.
      import_paths = current_sys_path
      final_module = module

      if item['level'] >= 1:
        # relative import, resolve the correct import path and module name.
        path = filename
        final_module = module_name
        for unused_i in range(item['level']):
          path = os.path.dirname(path)
          final_module, unused_sep, unused_tail = final_module.rpartition('.')
        import_paths = [path]
        if module:
          final_module = final_module + '.' + module

      try:
        module_subpaths.append(import_item)
        for idx, subpath in enumerate(module_subpaths):
          module_path, module_type = FindModule(subpath, import_paths)
          if (idx != len(module_subpaths) - 1 and
              module_type != imp.PKG_DIRECTORY):
            # We successfully imported something that is not package on non-last
            # part, so the last part is definitely not a module.
            import_is_module = False
            break
          import_paths = [module_path]
        else:
          # All imports goes well, the last part is a module.
          import_is_module = True
      except ImportError:
        # if import failed at any point, make some educated guess on whether
        # the last part is a module or method.
        # This can happen for external library dependency.
        if import_item[0].isupper():
          import_is_module = False
        else:
          import_is_module = True

      if import_is_module:
        final_module = final_module + '.' + import_item

      import_list.append(final_module)

  return sorted(set(import_list))


def LoadRules(path):
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
  for key, value in config[CONFIG_RULES].iteritems():
    # Expand value into imports
    imports = []
    for package in value:
      match = re.match(CONFIG_GROUP_PATTERN, package)
      if match:
        imports += groups[match.group(1)]
      else:
        imports.append(package)

    match = re.match(CONFIG_GROUP_PATTERN, key)
    if match:
      # Duplicate multiple rules
      for module in groups[match.group(1)]:
        rules[module] = imports
    else:
      rules[key] = imports

  def RulePriority(key):
    """Priority of a rule.

    Larger number means more strict and should be used first.
    """
    if key.startswith('='):
      return 4
    elif key.endswith('.*'):
      return 2
    elif key == '*':
      return 1
    else:
      return 3

  return sorted(rules.items(),
                key=lambda (k, unused_v): (RulePriority(k), k),
                reverse=True)


def GetPackage(module):
  """Gets the package name containing a module.

  Returns the module itself if it's top level.
  """
  if '.' in module:
    return module.rpartition('.')[0]
  else:
    return module


def RuleMatch(rule, module):
  """Check if a rule match a module.

  If the rule starts with a "=", then the rule would be matched against the
  whole module, else it would be matched against the package name.

  If the rule ends with ".*", the rule would match the module and all
  submodules of it.

  The rule can also be "*" to match everything.

  For example, the following (rule, module) match:
    (*, x.y)
    (=x.y.z, x.y.z)
    (x.y, x.y.z)
    (x.y.* x.y.z)
    (x.y.*, x.y.z.w)

  The following (rule, module) doesn't match:
    (=x.y.z, x.y.z.w)
    (x.y, x.y)
    (x.y, x.y.z.w)
    (x.y.*, x.y)
  """
  if rule == '*':
    return True

  if rule.startswith('='):
    target = module
    rule = rule[1:]
  else:
    target = GetPackage(module)

  if rule.endswith('.*'):
    return target == rule[:-2] or target.startswith(rule[:-1])
  else:
    return target == rule


def FindRule(rules, module):
  """Find the first matching rule in rules for module."""
  for key, value in rules:
    if RuleMatch(key, module):
      return value
  raise ValueError('Module %s not found in rule.' % module)


def CheckDependencyList(rules, module, import_list):
  """Check if a module's import list is prohibited by the rule.

  Returns the list of prohibited imports.
  """
  rule = FindRule(rules, module)

  result = []
  for item in import_list:
    bad = True
    if any(RuleMatch(r, item) for r in rule):
      bad = False
    if bad:
      result.append(item)

  return result


def Check(filename, rules):
  """Check the file dependency by rule."""
  if os.path.splitext(filename)[1] != '.py':
    return None
  if filename.endswith('_unittest.py'):
    return None

  try:
    filename = os.path.abspath(filename)
    module_name = GuessModule(filename)
    if module_name is None:
      raise ValueError("%s is not in factory Python directory." % filename)

    import_list = GetImportList(filename, module_name)
    import_list = [x for x in import_list if not GuessIsBuiltin(x)]

    bad_imports = CheckDependencyList(rules, module_name, import_list)
    if bad_imports:
      raise ValueError('\n'.join('  x %s' % x for x in bad_imports))
    return None
  except Exception as e:
    error_msg = '--- %s (%s) ---\n%s' % (os.path.relpath(filename), module_name,
                                         e)
    return error_msg


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      'sources', metavar='SOURCE_CODE', nargs='*',
      help='The Python source code to check dependencies')
  parser.add_argument(
      '--parallel', '-p',
      action='store_true',
      help='Run the dependency checks in parallel')
  args = parser.parse_args()

  rules = LoadRules(os.path.join(os.path.dirname(__file__), 'deps.conf'))

  pool = multiprocessing.Pool(multiprocessing.cpu_count()
                              if args.parallel else 1)

  return_value = 0
  for error_msg in pool.imap_unordered(
      functools.partial(Check, rules=rules), args.sources):
    if error_msg is not None:
      print(error_msg)
      return_value = 1
  pool.close()
  sys.exit(return_value)


if __name__ == '__main__':
  main()
