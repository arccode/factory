#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rf.tools.csv_reader import ReadCsv
from cros.factory.test.rf.tools.csv_reader import ReadCsvAsDict
from cros.factory.test.rf.tools.csv_reader import ReadCsvAsListOfDict
from cros.factory.test.rf.tools.csv_reader import ReadSingleCell


class CsvReaderTest(unittest.TestCase):

  def setUp(self):
    self.testdata_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), 'testdata')
    self.list_expected = [
        {'key1': 3, 'key2': 4},
        {'key1': 2, 'key2': 5},
        {'key1': None, 'key2': 8},
        {'key1': 1, 'key2': 9}]
    self.dict_expected = {'key1': 33, 'key2': 2}

  def testReadSingleCell(self):
    self.assertEqual(ReadSingleCell('100'), 100)
    self.assertEqual(ReadSingleCell("'str_test'"), 'str_test')
    self.assertEqual(ReadSingleCell('(300, 600)'), (300, 600))
    self.assertEqual(ReadSingleCell(''), None)
    self.assertEqual(ReadSingleCell('[1, 4, 7]'), [1, 4, 7])
    self.assertEqual(ReadSingleCell('[1, 4, 7]'), [1, 4, 7])
    self.assertRaisesRegexp(
        NameError, 'name .* is not defined',
        ReadSingleCell, 'invalid_syntax')
    self.assertRaisesRegexp(
        ValueError, 'Failed to load external',
        ReadSingleCell, "CsvLink('not_exist_file.csv')")

  def testReadCsvAsADict(self):
    loaded_dict = ReadCsvAsDict(
        os.path.join(self.testdata_path, 'dict_normal.csv'))
    self.assertEqual(loaded_dict, self.dict_expected)

  def testReadCsvAsADictInvalidColumns(self):
    self.assertRaisesRegexp(
        ValueError, 'Columns format is not a dict', ReadCsvAsDict,
        os.path.join(self.testdata_path, 'dict_invalid_column.csv'))

  def testReadCsvAsADictDuplicatedKey(self):
    self.assertRaisesRegexp(
        ValueError, 'Duplicated key', ReadCsvAsDict,
        os.path.join(self.testdata_path, 'dict_duplicated_key.csv'))

  def testReadCsvAsListOfDict(self):
    loaded_list = ReadCsvAsListOfDict(
        os.path.join(self.testdata_path, 'list_of_dict_normal.csv'))
    self.assertEqual(loaded_list, self.list_expected)

  def testReadCsvAsListOfDictDuplicatedColumn(self):
    self.assertRaisesRegexp(
        ValueError, 'Duplicated column', ReadCsvAsListOfDict,
        os.path.join(self.testdata_path, 'list_of_dict_duplicated_column.csv'))

  def testReadCsv(self):
    loaded_python_obj = ReadCsv(
        os.path.join(self.testdata_path, 'recursive_example.csv'))
    python_obj_expected = {'key1': self.dict_expected,
                           'key2': 33,
                           'key3': self.list_expected}
    self.assertEqual(loaded_python_obj, python_obj_expected)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
