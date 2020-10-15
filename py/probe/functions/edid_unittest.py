#!/usr/bin/env python3
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import binascii
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from cros.factory.probe.functions import edid
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils


def LoadJSONFromFile(path):
  with open(path) as f:
    value = json.load(f)
  return value


class EdidTest(unittest.TestCase):

  @mock.patch.object(edid, '_I2CDump', return_value=None)
  def testLoadFromI2c(self, MockI2CDump):
    self.assertIsNone(edid.LoadFromI2C(0))
    self.assertIsNone(edid.LoadFromI2C('/dev/i2c-0'))
    MockI2CDump.assert_called_with(
        '/dev/i2c-0', edid.I2C_LVDS_ADDRESS, edid.MINIMAL_SIZE)

  def testParser(self):
    # Public data from E-EDID spec,
    # http://read.pudn.com/downloads110/ebook/456020/E-EDID%20Standard.pdf
    edid_data = """
      00 FF FF FF FF FF FF 00 10 AC AB 50 00 00 00 00 2A 09 01 03 0E 26 1D 96 EF
      EE 91 A3 54 4C 99 26 0F 50 54 A5 43 00 A9 4F A9 59 71 59 61 59 45 59 31 59
      C2 8F 01 01 86 3D 00 C0 51 00 30 40 40 A0 13 00 7C 22 11 00 00 1E 00 00 00
      FF 00 35 35 33 34 37 42 4F 4E 5A 48 34 37 0A 00 00 00 FC 00 44 45 4C 4C 20
      55 52 31 31 31 0A 20 20 00 00 00 FD 00 30 A0 1E 79 1C 02 00 28 50 10 0E 80
      46 00 8D
      """
    edid_bin = binascii.unhexlify(''.join(edid_data.strip().split()))
    result = edid.Parse(edid_bin)
    self.assertEqual(result['width'], '1280')
    self.assertEqual(result['height'], '1024')
    self.assertEqual(result['vendor'], 'DEL')
    self.assertEqual(result['product_id'], '50ab')


class EDIDFunctionTest(unittest.TestCase):
  # Mocks edid.LoadFromFile and edid.LoadFromI2C by creating sysfs paths and I2C
  # paths in a new root, and read the parsed EDID directly from the files.
  FAKE_EDID = [
      {'vendor': 'IBM', 'product_id': '001', 'width': '111'},
      {'vendor': 'IBN', 'product_id': '002', 'width': '222'},
  ]
  FAKE_SYSFS_PATHS = ['sys/class/drm/A/edid', 'sys/class/drm/BB/edid']
  FAKE_I2C_PATHS = ['dev/i2c-1', 'dev/i2c-22']

  def setUp(self):
    self.root_dir = tempfile.mkdtemp(prefix='probe_edid_')
    self.InitEDIDFunction()

    self.patchers = []
    self.patchers.append(
        mock.patch('cros.factory.utils.sys_utils.LoadKernelModule'))
    self.patchers.append(
        mock.patch('cros.factory.probe.functions.edid.LoadFromFile',
                   side_effect=LoadJSONFromFile))
    self.patchers.append(
        mock.patch('cros.factory.probe.functions.edid.LoadFromI2C',
                   side_effect=LoadJSONFromFile))
    self.patchers.append(
        mock.patch('cros.factory.probe.functions.edid.EDIDFunction.ROOT_PATH',
                   self.root_dir))
    for patcher in self.patchers:
      patcher.start()

  def tearDown(self):
    if os.path.exists(self.root_dir):
      shutil.rmtree(self.root_dir)
    for patcher in self.patchers:
      patcher.stop()

  def WriteEDIDToRootDir(self, paths, values):
    for path, value in zip(paths, values):
      file_path = os.path.join(self.root_dir, path)
      dir_path = os.path.dirname(file_path)
      file_utils.TryMakeDirs(dir_path)
      json_utils.DumpFile(file_path, value)

  def SetupSysfsEDID(self):
    self.WriteEDIDToRootDir(self.FAKE_SYSFS_PATHS, self.FAKE_EDID)

  def SetupI2CEDID(self):
    self.WriteEDIDToRootDir(self.FAKE_I2C_PATHS, self.FAKE_EDID)

  def InitEDIDFunction(self):
    edid.EDIDFunction.path_to_identity = {}
    edid.EDIDFunction.identity_to_edid = {}

  def testSysfs(self, *unused_mocks):
    # Set up both sysfs and I2C EDID. The probe function should only read from
    # sysfs.
    self.SetupSysfsEDID()
    self.SetupI2CEDID()

    expected_result = [
        dict(self.FAKE_EDID[0],
             sysfs_path=os.path.join(self.root_dir, self.FAKE_SYSFS_PATHS[0])),
        dict(self.FAKE_EDID[1],
             sysfs_path=os.path.join(self.root_dir, self.FAKE_SYSFS_PATHS[1]))]

    result = edid.EDIDFunction()()
    self.assertCountEqual(result, expected_result)

    for i in range(2):
      result = edid.EDIDFunction(
          path=os.path.join(self.root_dir, self.FAKE_SYSFS_PATHS[i]))()
      self.assertCountEqual(result, [expected_result[i]])

  def testI2C(self, *unused_mocks):
    # Don't set up sysfs EDID. The probe function will read from I2C.
    self.SetupI2CEDID()

    expected_result = [
        dict(self.FAKE_EDID[0],
             dev_path=os.path.join(self.root_dir, self.FAKE_I2C_PATHS[0])),
        dict(self.FAKE_EDID[1],
             dev_path=os.path.join(self.root_dir, self.FAKE_I2C_PATHS[1]))]

    result = edid.EDIDFunction()()
    self.assertCountEqual(result, expected_result)

    for i in range(2):
      result = edid.EDIDFunction(
          path=os.path.join(self.root_dir, self.FAKE_I2C_PATHS[i]))()
      self.assertCountEqual(result, [expected_result[i]])

    result = edid.EDIDFunction(path='22')()
    self.assertCountEqual(result, [expected_result[1]])


if __name__ == '__main__':
  unittest.main()
