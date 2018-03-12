#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import pci
from cros.factory.utils import  file_utils


def _AddBusType(results):
  for result in results:
    result['bus_type'] = 'pci'
  return results


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
    for key, value in values.iteritems():
      if key == 'revision_id':
        open(os.path.join(real_path, 'config'), 'wb').write(
            'x' * 8 + chr(int(value, 16)))
      else:
        file_utils.WriteFile(os.path.join(real_path, key), value)

    link_name = os.path.join(
        self.my_root, 'sys', 'bus', 'pci', 'devices', pci_name)
    file_utils.TryMakeDirs(os.path.dirname(link_name))
    file_utils.ForceSymlink(real_path, link_name)

  def testNormal(self):
    values1 = {'vendor': '1234', 'device': '5678', 'revision_id': '0x14'}
    self._CreatePCIDevice('dev1', '/sys/devices/pci1/xxyy', values1)

    values2 = {'vendor': '1357', 'device': '2468', 'revision_id': '0x34'}
    self._CreatePCIDevice('dev2', '/sys/devices/pci1/aabb', values2)

    values3 = {'vendor': 'xxxx'}
    self._CreatePCIDevice('dev3', '/sys/devices/pci1/xxxx', values3)

    func = pci.PCIFunction()
    self.assertEquals(sorted(func()), _AddBusType(sorted([values1, values2])))

    func = pci.PCIFunction(dir_path=self.my_root + '/sys/devices/pci1/xxyy')
    self.assertEquals(func(), _AddBusType([values1]))


if __name__ == '__main__':
  unittest.main()
