#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.probe.functions import generic_storage


def ReadFileBinaryModeTransform(data):
  """probe.functions.file.ReadFile does this transformation in binary mode."""
  binary_data = ['0x%02x' % char for char in data]
  return ' '.join(binary_data)


def CreateFakeReadFileFunc(file_contents):
  return lambda path, *args, **kwargs: file_contents[path]


class GenericStorageFunctionTest(unittest.TestCase):
  """Unit tests for generic_storage."""

  @mock.patch('generic_storage.file_module.ReadFile')
  def testGetShortNVMeStorageFirmwareVersion(self, read_file_mock):
    read_file_mock.side_effect = CreateFakeReadFileFunc({
        'fake_node/device/fwrev': '',
        'fake_node/device/firmware_rev': ReadFileBinaryModeTransform(b'HPS2\n'),
    })
    self.assertEqual(
        generic_storage.GetStorageFirmwareVersion('fake_node'),
        '485053320a000000 (HPS2)')

  @mock.patch('generic_storage.file_module.ReadFile')
  def testGetFullNVMeStorageFullFirmwareVersion(self, read_file_mock):
    read_file_mock.side_effect = CreateFakeReadFileFunc({
        'fake_node/device/fwrev':
            '',
        'fake_node/device/firmware_rev':
            ReadFileBinaryModeTransform(b'EXH7201Q'),
    })
    self.assertEqual(
        generic_storage.GetStorageFirmwareVersion('fake_node'),
        '4558483732303151 (EXH7201Q)')


if __name__ == '__main__':
  unittest.main()
