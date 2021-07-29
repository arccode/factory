#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

from cros.factory.probe.functions import pci
from cros.factory.utils import file_utils


class PCIFunctionTest(unittest.TestCase):

  def setUp(self):
    self.my_root = tempfile.mkdtemp()

    self.orig_glob_path = pci.PCIFunction.GLOB_PATH
    pci.PCIFunction.GLOB_PATH = self.my_root + pci.PCIFunction.GLOB_PATH

  def tearDown(self):
    pci.PCIFunction.GLOB_PATH = self.orig_glob_path

  def _CreatePCIDevice(self, pci_name, real_path, values):
    real_path = self.my_root + real_path

    file_utils.TryMakeDirs(real_path)
    for key, value in values.items():
      if key == 'revision_id':
        file_utils.WriteFile(
            os.path.join(real_path, 'config'),
            b'x' * 8 + bytes([int(value, 16)]), encoding=None)
      else:
        file_utils.WriteFile(os.path.join(real_path, key), value)

    link_name = os.path.join(self.my_root, 'sys', 'bus', 'pci', 'devices',
                             pci_name)
    file_utils.TryMakeDirs(os.path.dirname(link_name))
    file_utils.ForceSymlink(real_path, link_name)

  def testNormal(self):
    values1 = {
        'class': '010203',
        'vendor': 'dev1',
        'device': '5678',
        'revision_id': '0x14'
    }
    self._CreatePCIDevice('dev1', '/sys/devices/pci1/xxyy', values1)

    values2 = {
        'class': '040506',
        'vendor': 'dev2',
        'device': '2468',
        'revision_id': '0x34'
    }
    self._CreatePCIDevice('dev2', '/sys/devices/pci1/aabb', values2)

    values3 = {
        'vendor': 'dev3'
    }
    self._CreatePCIDevice('dev3', '/sys/devices/pci1/xxxx', values3)

    func = pci.PCIFunction()
    self.assertCountEqual(func(), self._AddExtraFields([values1, values2]))

    func = pci.PCIFunction(dir_path=self.my_root + '/sys/devices/pci1/xxyy')
    self.assertCountEqual(func(), self._AddExtraFields([values1]))

  def _AddExtraFields(self, values):
    for value in values:
      value['device_path'] = os.path.join(self.my_root, 'sys', 'bus', 'pci',
                                          'devices', value['vendor'])
      value['bus_type'] = 'pci'
    return values


if __name__ == '__main__':
  unittest.main()
