#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for json_utils.py."""

import os
import unittest

from cros.factory.utils import file_utils
from cros.factory.utils import json_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__),
                               'testdata', 'json_utils_unittest.json')


class _TestCaseBase(unittest.TestCase):
  def assertJSONObjEqual(self, a, b):
    if isinstance(a, list):
      self.assertIsInstance(b, list)
      self.assertEqual(len(a), len(b))
      for element_a, element_b in zip(a, b):
        self.assertJSONObjEqual(element_a, element_b)
    elif isinstance(a, dict):
      self.assertIsInstance(b, dict)
      self.assertEqual(len(a), len(b))
      for key, value in a.items():
        self.assertJSONObjEqual(value, b[key])
    else:
      self.assertIs(type(a), type(b))
      self.assertEqual(a, b)


class LoadStrTest(_TestCaseBase):
  _TEST_DATA = '{"aaa": [3, false, null, "bbb"]}'

  def testLoadStr(self):
    self.assertJSONObjEqual(
        json_utils.LoadStr(self._TEST_DATA),
        {'aaa': [3, False, None, "bbb"]})


class LoadFileTest(_TestCaseBase):
  def testLoadFile(self):
    self.assertJSONObjEqual(
        json_utils.LoadFile(_TEST_DATA_PATH),
        {'aaa': 'bbb', 'ccc': ['ddd', {}, 'fff']})


# For dumping related tests, just check whether the dumped output can be loaded
# back or not.

class DumpStrTest(_TestCaseBase):
  _TEST_DATA = {'aaa': [3, False, None, 'bbb']}

  def testNormal(self):
    for kwargs in [{}, {'pretty': False}, {'pretty': True}]:
      json_str = json_utils.DumpStr(self._TEST_DATA, **kwargs)
      self.assertJSONObjEqual(json_utils.LoadStr(json_str), self._TEST_DATA)


class DumpFileTest(_TestCaseBase):
  _TEST_DATA = {'aaa': [3, False, None, 'bbb']}

  def testNormal(self):
    for kwargs in [{}, {'pretty': False}, {'pretty': True}]:
      with file_utils.UnopenedTemporaryFile() as path:
        json_utils.DumpFile(path, self._TEST_DATA, **kwargs)
        self.assertJSONObjEqual(json_utils.LoadFile(path), self._TEST_DATA)


class JSONDatabaseTest(_TestCaseBase):
  def testNormal(self):
    with file_utils.TempDirectory() as dir_path:
      db_path = os.path.join(dir_path, 'db')

      db = json_utils.JSONDatabase(db_path, allow_create=True)
      self.assertJSONObjEqual(db, {})

      db['aaa'] = 'bbb'
      db['ccc'] = [1, None, {'ddd': 'eee'}]
      self.assertJSONObjEqual(
          db, {'aaa': 'bbb', 'ccc': [1, None, {'ddd': 'eee'}]})

      db.Save()
      db2 = json_utils.JSONDatabase(db_path)
      self.assertJSONObjEqual(
          db2, {'aaa': 'bbb', 'ccc': [1, None, {'ddd': 'eee'}]})


if __name__ == '__main__':
  unittest.main()
