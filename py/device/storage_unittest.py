#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import storage


class StorageDictTest(unittest.TestCase):
  """Unittest for DUT storage Dict APIs."""

  def setUp(self):
    self.dut = mock.MagicMock()
    self.storage = storage.Storage(self.dut)
    self.dict_file_path = '/path/to/dict/file'
    self.storage.GetDictFilePath = lambda: self.dict_file_path

  def testLoadDictFileNotExists(self):
    self.dut.path.exists = mock.Mock(return_value=False)

    self.assertEqual({}, self.storage.LoadDict())

    self.dut.path.exists.assert_called_with(self.dict_file_path)

  def testLoadDictFileExists(self):
    data = {'k1': 'v1', 'k2': 123}
    self.dut.path.exists = mock.Mock(return_value=True)
    self.dut.ReadFile = mock.Mock(return_value=json.dumps(data))

    self.assertEqual(data, self.storage.LoadDict())

    self.dut.path.exists.assert_called_with(self.dict_file_path)
    self.dut.ReadFile.assert_called_with(self.dict_file_path)

  def testLoadDictInvalidJSONFormat(self):
    self.dut.path.exists = mock.Mock(return_value=True)
    self.dut.ReadFile = mock.Mock(return_value='!@#$%^&*()[]{}')

    self.assertEqual({}, self.storage.LoadDict())

    self.dut.path.exists.assert_called_with(self.dict_file_path)
    self.dut.ReadFile.assert_called_with(self.dict_file_path)

  def testLoadDictNotDictionary(self):
    data = [('k1', 'v1'), ('k2', 123)]
    self.dut.path.exists = mock.Mock(return_value=True)
    self.dut.ReadFile = mock.Mock(return_value=json.dumps(data))

    self.assertEqual({}, self.storage.LoadDict())

    self.dut.path.exists.assert_called_with(self.dict_file_path)
    self.dut.ReadFile.assert_called_with(self.dict_file_path)

  def testSaveDictNotDictionary(self):
    data = [('k1', 'v1'), ('k2', 123)]
    with self.assertRaises(AssertionError):
      self.storage.SaveDict(data)

  def testSaveDictIgnoreNonStringKeys(self):
    data = {1: 'int', '1': 'str', 2: 'int', 3.5: 'float'}
    saved_data = {'1': 'str'}
    saved_string = json.dumps(saved_data, sort_keys=True)
    dict_file_dirname = '/path/to/dir'

    self.dut.path.dirname = mock.Mock(return_value=dict_file_dirname)

    self.assertEqual(self.storage.SaveDict(data), saved_data)

    self.dut.CheckCall.assert_called_with(['mkdir', '-p', dict_file_dirname])
    self.dut.path.dirname.assert_called_with(self.dict_file_path)
    self.dut.WriteFile.assert_called_with(self.dict_file_path, saved_string)

  def testUpdateDict(self):
    data = {'a': 'b', 'c': 'd'}
    update = {'c': 'x', 'k': 'v'}
    updated_data = {'a': 'b', 'c': 'x', 'k': 'v'}
    return_value = 'MOCKED_RETURN_VALUE'

    self.storage.LoadDict = mock.Mock(return_value=data)
    self.storage.SaveDict = mock.Mock(return_value=return_value)

    self.assertEqual(return_value,
                     self.storage.UpdateDict(update))

    self.storage.LoadDict.assert_called_with()
    self.storage.SaveDict.assert_called_with(updated_data)

  def testDeleteDictKeyExists(self):
    data = {'a': 'b', 'c': 'd'}
    updated_data = {'c': 'd'}
    return_value = 'MOCKED_RETURN_VALUE'

    self.storage.LoadDict = mock.Mock(return_value=data)
    self.storage.SaveDict = mock.Mock(return_value=return_value)

    self.assertEqual(updated_data, self.storage.DeleteDict('a'))

    self.storage.LoadDict.assert_called_with()
    self.storage.SaveDict.assert_called_with(updated_data)

  def testDeleteDictKeyNotExists(self):
    data = {'a': 'b', 'c': 'd'}
    return_value = 'MOCKED_RETURN_VALUE'

    self.storage.LoadDict = mock.Mock(return_value=data)
    self.storage.SaveDict = mock.Mock(return_value=return_value)

    self.assertEqual(data, self.storage.DeleteDict('k'))

    self.storage.LoadDict.assert_called_with()
    self.storage.SaveDict.assert_not_called()


if __name__ == '__main__':
  unittest.main()
