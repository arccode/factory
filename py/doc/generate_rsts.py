#!/usr/bin/env python2
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
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
import inspect
import logging
import os
import re
import StringIO

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function as probe_function
from cros.factory.test.env import paths
from cros.factory.test.test_lists import manager
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils.type_utils import Enum


DOC_GENERATORS = {}

def DocGenerator(dir_name):
  def Decorator(func):
    assert dir_name not in DOC_GENERATORS
    DOC_GENERATORS[dir_name] = func
    return func

  return Decorator


def Escape(text):
  r"""Escapes characters that must be escaped in a raw tag (*, `, and \)."""
  return re.sub(r'([*`\\])', '\\\\\\1', text)


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


def LinkToDoc(name, path):
  """Create a hyper-link tag which links to another document file.

  Args:
    name: The tag name.
    path: Path of the target document, either absolute or relative.
  """
  return ':doc:`%s <%s>`' % (Escape(name), Escape(path))


class RSTWriter(object):
  def __init__(self, io):
    self.io = io

  def WriteTitle(self, title, mark, ref_label=None):
    if ref_label:
      self.io.write('.. _%s:\n\n' % Escape(ref_label))
    self.io.write(title + '\n')
    self.io.write(mark * len(title) + '\n')

  def WriteParagraph(self, text):
    self.io.write(text + '\n\n')

  def WriteListItem(self, content):
    self.WriteParagraph('- ' + content)

  def WriteListTableHeader(self, widths=None, header_rows=None):
    self.io.write('.. list-table::\n')
    if widths is not None:
      self.io.write('   :widths: %s\n' % ' '.join(map(str, widths)))
    if header_rows is not None:
      self.io.write('   :header-rows: %d\n' % header_rows)
    self.io.write('\n')

  def WriteListTableRow(self, row):
    for i, cell in enumerate(row):
      # Indent the first line with " - " (or " * - " if it's the first
      # column)
      self.io.write(Indent(cell, ' ' * 7, '   * - ' if i == 0 else '     - '))
      self.io.write('\n')
    self.io.write('\n')


def WriteArgsTable(rst, title, args):
  """Writes a table describing arguments.

  Args:
    rst: An instance of RSTWriter for writting RST context.
    title: The title of the arguments section.
    args: A list of Arg objects, as in the ARGS attribute of a pytest.
  """
  rst.WriteTitle(title, '-')

  if not args:
    rst.WriteParagraph('This test does not have any arguments.')
    return

  rst.WriteListTableHeader(widths=(20, 10, 60), header_rows=1)
  rst.WriteListTableRow(('Name', 'Type', 'Description'))

  for arg in args:
    description = arg.help.strip()

    annotations = []
    if arg.IsOptional():
      annotations.append('optional')
      annotations.append('default: ``%s``' % Escape(repr(arg.default)))
    if annotations:
      description = '(%s) %s' % ('; '.join(annotations), description)

    def FormatArgType(arg_type):
      if isinstance(arg_type, Enum):
        return repr(sorted(arg_type))
      elif arg_type == type(None):
        return 'None'
      else:
        return arg_type.__name__
    arg_types = ', '.join(FormatArgType(x) for x in arg.type)

    rst.WriteListTableRow((arg.name, arg_types, description))


def GenerateTestDocs(rst, pytest_name):
  """Generates test docs for a pytest.

  Args:
    rst: A stream to write to.
    pytest_name: The name of pytest under package cros.factory.test.pytests.

  Returns:
    The first line of the docstring.
  """
  module = pytest_utils.LoadPytestModule(pytest_name)
  test_case = pytest_utils.FindTestCase(module)

  args = getattr(test_case, 'ARGS', [])

  doc = getattr(module, '__doc__', None)
  if doc is None:
    doc = 'No test-level description available for pytest %s.' % pytest_name
  if isinstance(doc, str):
    doc = doc.decode('utf-8')

  rst.WriteTitle(pytest_name, '=')
  rst.WriteParagraph(doc)
  WriteArgsTable(rst, 'Test Arguments', args)

  # Remove everything after the first pair of newlines.
  return re.sub(r'(?s)\n\s*\n.+', '', doc).strip()


@DocGenerator('pytests')
def GeneratePyTestsDoc(pytests_output_dir):
  # Map of pytest name to info returned by GenerateTestDocs.
  pytest_info = {}

  for relpath in pytest_utils.GetPytestList(paths.FACTORY_DIR):
    pytest_name = pytest_utils.RelpathToPytestName(relpath)
    with codecs.open(
        os.path.join(pytests_output_dir, pytest_name + '.rst'),
        'w', 'utf-8') as out:
      try:
        pytest_info[pytest_name] = GenerateTestDocs(RSTWriter(out), pytest_name)
      except Exception:
        logging.warn('Failed to generate document for pytest %s.', pytest_name)

  index_rst = os.path.join(pytests_output_dir, 'index.rst')
  with open(index_rst, 'a') as f:
    rst = RSTWriter(f)
    for k, v in sorted(pytest_info.iteritems()):
      rst.WriteListTableRow((LinkToDoc(k, k), v))


def WriteTestObjectDetail(
    rst,
    test_object_name,
    test_object):
  """Writes a test_object to output stream.

  Args:
    rst: An instance of RSTWriter for writing RST context.
    test_object_name: name of the test object (string).
    test_object: a test_object defined by JSON test list.
  """
  rst.WriteTitle(Escape(test_object_name), '-')

  if '__comment' in test_object:
    rst.WriteParagraph(Escape(test_object['__comment']))

  if test_object.get('args'):
    rst.WriteTitle('args', '`')
    for key, value in test_object['args'].iteritems():
      formatted_value = json_utils.DumpStr(value, pretty=True)
      formatted_value = '::\n\n' + Indent(formatted_value, '  ')
      formatted_value = Indent(formatted_value, '  ')
      rst.WriteParagraph('``{key}``\n{value}'.format(
          key=key, value=formatted_value))


@DocGenerator('test_lists')
def GenerateTestListDoc(output_dir):
  manager_ = manager.Manager()
  manager_.BuildAllTestLists()

  for test_list_id in manager_.GetTestListIDs():
    out_path = os.path.join(output_dir, test_list_id + '.test_list.rst')

    with open(out_path, 'w') as out:
      rst = RSTWriter(out)

      logging.warn('processing test list %s', test_list_id)
      test_list = manager_.GetTestListByID(test_list_id)
      config = test_list.ToTestListConfig()
      raw_config = manager_.loader.Load(test_list_id, allow_inherit=False)

      rst.WriteTitle(test_list_id, '=')

      if raw_config.get('__comment'):
        rst.WriteParagraph(Escape(raw_config['__comment']))

      rst.WriteTitle('Inherit', '-')
      for parent in raw_config.get('inherit', []):
        rst.WriteListItem(LinkToDoc(parent, parent))

      rst.WriteTitle('Definitions', '-')
      rst.WriteParagraph('Only pytest definitions are listed.')

      rst_define = RSTWriter(StringIO.StringIO())
      rst_detail = RSTWriter(StringIO.StringIO())

      rst_define.WriteListTableHeader(header_rows=1)
      rst_define.WriteListTableRow(('Defined Name', 'Pytest Name'))

      has_definitions = False
      for test_object_name in sorted(raw_config['definitions'].keys()):
        test_object = config['definitions'][test_object_name]
        test_object = test_list.ResolveTestObject(
            test_object, test_object_name, cache={})
        if test_object.get('pytest_name'):
          has_definitions = True
          pytest_name = test_object['pytest_name']
          doc_path = os.path.join('..', 'pytests', pytest_name)
          rst_define.WriteListTableRow(('`%s`_' % Escape(test_object_name),
                                        LinkToDoc(pytest_name, doc_path)))

          WriteTestObjectDetail(rst_detail, test_object_name, test_object)

      if has_definitions:
        rst.WriteParagraph(rst_define.io.getvalue())
        rst.WriteParagraph(rst_detail.io.getvalue())


def FinishTemplate(path, **kwargs):
  template = file_utils.ReadFile(path)
  file_utils.WriteFile(path, template.format(**kwargs))


def GetModuleClassDoc(cls):
  # Remove the indent.
  s = re.sub(r'^  ', '', cls.__doc__ or '', flags=re.M)

  return tuple(t.strip('\n')
               for t in re.split(r'\n\s*\n', s + '\n\n', maxsplit=1))


def GenerateProbeFunctionDoc(functions_path, func_name, func_cls):
  short_desc, main_desc = GetModuleClassDoc(func_cls)

  with open(os.path.join(functions_path, func_name + '.rst'), 'w') as f:
    rst = RSTWriter(f)
    rst.WriteTitle(func_name, '=')
    rst.WriteParagraph(short_desc)
    WriteArgsTable(rst, 'Function Arguments', func_cls.ARGS)
    rst.WriteParagraph(main_desc)

  return short_desc, os.path.join(os.path.basename(functions_path), func_name)


@DocGenerator('probe')
def GenerateProbeDoc(output_dir):
  func_tables = {}
  def _AppendToFunctionTable(func_cls, row):
    all_base_cls = inspect.getmro(func_cls)
    base_cls_index = all_base_cls.index(probe_function.Function) - 1
    if base_cls_index == 0:
      func_type = 'Misc'
      type_desc = ''
    else:
      func_type = all_base_cls[base_cls_index].__name__
      type_desc = GetModuleClassDoc(all_base_cls[base_cls_index])[1]

    if func_type not in func_tables:
      rst = func_tables[func_type] = RSTWriter(StringIO.StringIO())
      rst.WriteTitle(func_type, '`', ref_label=func_type)
      rst.WriteParagraph(type_desc)
      rst.WriteListTableHeader(header_rows=1)
      rst.WriteListTableRow(('Function Name', 'Short Description'))

    func_tables[func_type].WriteListTableRow(row)

  functions_path = os.path.join(output_dir, 'functions')
  file_utils.TryMakeDirs(functions_path)

  # Parse all functions.
  probe_function.LoadFunctions()
  for func_name in sorted(probe_function.GetRegisteredFunctions()):
    func_cls = probe_function.GetFunctionClass(func_name)

    short_desc, doc_path = GenerateProbeFunctionDoc(
        functions_path, func_name, func_cls)
    _AppendToFunctionTable(
        func_cls, (LinkToDoc(func_name, doc_path), short_desc))

  # Generate list tables of all functions, category by the function type.
  functions_section_rst = RSTWriter(StringIO.StringIO())

  # Always render `Misc` section at the end.
  func_types = sorted(func_tables.keys())
  if 'Misc' in func_types:
    func_types.remove('Misc')
    func_types.append('Misc')

  for func_type in func_types:
    func_table_rst = func_tables[func_type]
    functions_section_rst.WriteParagraph(func_table_rst.io.getvalue())

  # Generate the index file.
  FinishTemplate(os.path.join(output_dir, 'index.rst'),
                 functions_section=functions_section_rst.io.getvalue())


def main():
  parser = argparse.ArgumentParser(
      description='Generate .rst files for the factory toolkit')
  parser.add_argument('--output-dir', '-o',
                      help='Output directory (default: %default)', default='.')
  args = parser.parse_args()

  for dir_name, func in DOC_GENERATORS.iteritems():
    full_path = os.path.join(args.output_dir, dir_name)
    file_utils.TryMakeDirs(full_path)
    func(full_path)


if __name__ == '__main__':
  main()
