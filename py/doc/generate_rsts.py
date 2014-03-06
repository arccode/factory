#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Generates some .rst files used to document parts of the factory toolkit.

Currently this generates a list of all available pytests, in the
doc/pytests directory.  In the future it may be extended to generate,
for example, a test list tree.

(Ideally these could be generated via Sphinx extensions, but this is not
always practical.)
"""


import argparse
import codecs
import importlib
import inspect
import logging
import os
import re
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.test import pytests
from cros.factory.test.utils import Enum
from cros.factory.utils import file_utils


def Escape(text):
  """Escapes characters that must be escaped in a raw tag (*, `, and \)."""
  return re.sub(r"([*`\\])", '\\\\\\1', text)


def Indent(text, prefix, first_line_prefix=None):
  """Indents a string.

  Args:
    text: The input string.
    prefix: The string to insert at the beginning of each line.
    first_line_prefix: The string to insert at the beginning of the first line.
        Defaults to prefix if unspecified.
  """
  if first_line_prefix is None:
    first_line_prefix = prefix

  return re.sub(
    '(?m)^',
    lambda match: first_line_prefix if match.start() == 0 else prefix,
    text)


def WriteTestArgs(args, out):
  """Writes a table describing test arguments.

  Args:
    args: A list of Arg objects, as in the ARGS attribute of a pytest.
    out: A stream to write to.
  """
  if not args:
    out.write('This test does not have any arguments.')
    return

  out.write(
    'Test Arguments\n'
    '--------------\n'
    '.. list-table::\n'
    '   :widths: 20 10 60\n'
    '   :header-rows: 1\n'
    '\n')

  def WriteRow(cols):
    for i, col in enumerate(cols):
      # Indent the first line with " - " (or " * - " if it's the first
      # column)
      out.write(Indent(col, ' ' * 7, '   * - ' if i == 0 else '     - '))
      out.write('\n')

  WriteRow(('Name', 'Type', 'Description'))
  for arg in args:
    description = arg.help.strip()

    annotations = []
    if arg.optional:
      annotations.append('optional')
    if arg.default is not None:
      annotations.append('default: ``%s``' % Escape(repr(arg.default)))
    if annotations:
      description = '(%s) %s' % ('; '.join(annotations), description)

    def FormatArgType(arg_type):
      if isinstance(arg_type, Enum):
        return '[' + ', '.join(str(x) for x in sorted(arg_type)) + ']'
      elif arg_type == type(None):
        return 'None'
      else:
        return arg_type.__name__
    arg_types = ', '.join(FormatArgType(x) for x in arg.type)

    WriteRow((arg.name, arg_types, description))


def GenerateTestDocs(pytest_name, module, out):
  """Generates test docs for a pytest.

  Args:
    pytest_name: The name of the pytest (e.g., 'foo' for foo.py).
    module: The module of the pytest.  This may be the module itself,
        or the name of the module (e.g., cros.factory.test.pytest.foo).
    out: A stream to write to.

  Returns:
    A dictionary of information about the test.  Currently this is just

      dict(short_docstring=short_docstring)

    where short_docstring is the first line of the docstring.
  """
  if isinstance(module, str):
    module_name = module
    try:
      module = importlib.import_module(module_name)
    except ImportError:
      logging.warn('Unable to import %s', module_name)
      return

  # Find the TestCase object.
  test_cases = [v for v in module.__dict__.itervalues()
                if inspect.isclass(v) and issubclass(v, unittest.TestCase)]
  if not test_cases:
    logging.warn('No test cases found in %s', module.__name__)
    return
  if len(test_cases) > 1:
    logging.warn('Expected only one test case in %s but found %r',
                 module.__name__, test_cases)
    return

  test_case = test_cases[0]
  args = getattr(test_case, 'ARGS', [])

  doc = getattr(module, '__doc__', None)
  if doc is None:
    doc = 'No test-level description available for pytest %s.' % pytest_name

  if isinstance(doc, str):
    doc = doc.decode('utf-8')

  out.write(pytest_name + '\n')
  out.write('=' * len(pytest_name) + '\n')
  out.write(doc)
  out.write('\n\n')

  WriteTestArgs(args, out)
  # Remove everything after the first pair of newlines.
  short_docstring = re.sub('(?s)\n\s*\n.+', '', doc).strip()
  return dict(short_docstring=short_docstring)


def main():
  parser = argparse.ArgumentParser(
      description="Generate .rst files for the factory toolkit")
  parser.add_argument('--output-dir', '-o',
                      help='Output directory (default: %default)', default='.')
  args = parser.parse_args()

  pytests_output_dir = os.path.join(args.output_dir, 'pytests')
  file_utils.TryMakeDirs(pytests_output_dir)

  pytest_module_dir = os.path.dirname(pytests.__file__)

  # Map of pytest name to info returned by GenerateTestDocs.
  pytest_info = {}

  for root, dummy_dirs, files in os.walk(pytest_module_dir):
    for f in files:
      if (not f.endswith('.py') or
          f.startswith('__') or
          f == 'factory_common.py' or
          f.endswith('_automator.py') or
          f.endswith('_e2etest.py') or
          f.endswith('_unittest.py') or
          f.endswith('_impl.py')):
        continue

      # E.g., "foo.py" or "foo/foo.py"
      relpath = os.path.relpath(os.path.join(root, f),
                                pytest_module_dir)
      # E.g., "foo" or "foo/foo"
      base = os.path.splitext(relpath)[0]

      if '/' in relpath:
        # It's in a subpackage.  Accept it only if it looks like
        # foo/foo.py.
        dirname, filename = os.path.split(base)
        if dirname != filename:
          continue

      module_name = ('cros.factory.test.pytests.' +
                     base.replace('/', '.'))
      pytest_name = os.path.basename(base)

      with codecs.open(os.path.join(pytests_output_dir, pytest_name + '.rst'),
                       'w', 'utf-8') as out:
        pytest_info[pytest_name] = GenerateTestDocs(
          pytest_name, module_name, out)

  index_rst = os.path.join(pytests_output_dir, 'index.rst')
  with open(index_rst, 'a') as f:
    for k, v in sorted(pytest_info.items()):
      f.write('   * - `%s <%s.html>`_\n' % (k, k))
      f.write(Indent(v['short_docstring'], ' ' * 7, '     - '))
      f.write('\n')

if __name__ == '__main__':
  main()

