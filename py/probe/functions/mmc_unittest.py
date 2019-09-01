#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import mmc
from cros.factory.utils import file_utils


class MMCFunctionTest(unittest.TestCase):
  def setUp(self):
    self.my_root = tempfile.mkdtemp()

    self.orig_glob_path = mmc.MMCFunction.GLOB_PATH
    mmc.MMCFunction.GLOB_PATH = self.my_root + mmc.MMCFunction.GLOB_PATH

  def tearDown(self):
    mmc.MMCFunction.GLOB_PATH = self.orig_glob_path

  def _CreateMMCDevice(self, mmc_name, real_path, values):
    real_path = self.my_root + real_path

    file_utils.TryMakeDirs(real_path)
    for key, value in values.iteritems():
      file_utils.WriteFile(os.path.join(real_path, key), value)

    link_name = os.path.join(
        self.my_root, 'sys', 'bus', 'mmc', 'devices', mmc_name)
    file_utils.TryMakeDirs(os.path.dirname(link_name))
    file_utils.ForceSymlink(real_path, link_name)

  def testNormal(self):
    values1 = {'cid': 'mmc1', 'csd': 'ss', 'fwrev': 'ff', 'hwrev': 'hh',
               'manfid': 'mm', 'oemid': 'oo', 'name': 'nn', 'serial': 'ss'}
    self._CreateMMCDevice('mmc1', '/sys/devices/mmc1', values1)

    values2 = {'cid': 'mmc2', 'csd': 'ss2',
               'manfid': 'mm2', 'oemid': 'oo2', 'name': 'n1', 'serial': 's2'}
    self._CreateMMCDevice('mmc2', '/sys/devices/mmc2', values2)

    values3 = {'cid': 'mmc3'}
    self._CreateMMCDevice('mmc3', '/sys/devices/mmc3', values3)

    func = mmc.MMCFunction()
    self.assertItemsEqual(func(), self._AddExtraFields([values1, values2]))

    func = mmc.MMCFunction(dir_path=self.my_root + '/sys/devices/mmc1')
    self.assertItemsEqual(func(), self._AddExtraFields([values1]))

  def _AddExtraFields(self, values):
    for value in values:
      value['device_path'] = os.path.join(
          self.my_root, 'sys', 'bus', 'mmc', 'devices', value['cid'])
      value['bus_type'] = 'mmc'

    return values


if __name__ == '__main__':
  unittest.main()
