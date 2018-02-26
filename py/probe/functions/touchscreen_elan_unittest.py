#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import touchscreen_elan
from cros.factory.utils import file_utils


class TouchscreenElanFunctionTest(unittest.TestCase):
  def setUp(self):
    self.func = touchscreen_elan.TouchscreenElanFunction()
    self.orig_dir = self.func.I2C_DEVICES_PATH
    self.tmp_dir = self.func.I2C_DEVICES_PATH = tempfile.mkdtemp()

    file_utils.WriteFile(os.path.join(self.tmp_dir, 'elants_i2c'), '')
    file_utils.WriteFile(os.path.join(self.tmp_dir, 'xxx'), '')

  def tearDown(self):
    self.func.I2C_DEVICES_PATH = self.orig_dir

  @mock.patch('cros.factory.probe.functions.sysfs.ReadSysfs')
  def testNormal(self, read_sysfs_mock):
    self._CreateDevice('dev1', {}, {'driver': '../elants_i2c'})
    self.assertEquals(self.func.Probe(),
                      [read_sysfs_mock.return_value])

  @mock.patch('cros.factory.probe.functions.sysfs.ReadSysfs')
  def testDriverIsNotALink(self, unused_read_sysfs_mock):
    self._CreateDevice('dev1', {'driver': '../elants_i2c'}, {})
    self.assertEquals(self.func.Probe(), [])

  @mock.patch('cros.factory.probe.functions.sysfs.ReadSysfs')
  def testNotCorrectDriver(self, unused_read_sysfs_mock):
    self._CreateDevice('dev1', {'driver': '../xxx'}, {})
    self.assertEquals(self.func.Probe(), [])

  @mock.patch('cros.factory.probe.functions.sysfs.ReadSysfs',
              return_value=None)
  def testBadSysfsDir(self, unused_read_sysfs_mock):
    self._CreateDevice('dev1', {}, {'driver': '../elants_i2c'})
    self.assertEquals(self.func.Probe(), [])

  def _CreateDevice(self, name, files, links):
    file_utils.TryMakeDirs(os.path.join(self.tmp_dir, 'devices', name))
    for file_name, file_content in files.iteritems():
      path = os.path.join(self.tmp_dir, 'devices', name, file_name)
      file_utils.WriteFile(path, file_content)
    for link_name, link_target in links.iteritems():
      path = os.path.join(self.tmp_dir, 'devices', link_name)
      file_utils.ForceSymlink(link_target, path)


if __name__ == '__main__':
  unittest.main()
