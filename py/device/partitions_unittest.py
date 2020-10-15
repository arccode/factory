#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit test for partitions module."""

import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import partitions


class PartitionsTest(unittest.TestCase):
  """Unit test for Partition class."""

  def setUp(self):
    self.dut = mock.Mock(device_types.DeviceInterface)

  def testGetPartition(self):
    disk = partitions.Partitions(self.dut)
    self.dut.CheckOutput.return_value = '/dev/mmcblk0\n'

    self.assertEqual('/dev/mmcblk0p1', disk.STATEFUL.path)
    self.assertEqual('/dev/mmcblk0p2', disk.FACTORY_KERNEL.path)
    self.assertEqual('/dev/mmcblk0p3', disk.FACTORY_ROOTFS.path)
    self.assertEqual('/dev/mmcblk0p4', disk.RELEASE_KERNEL.path)
    self.assertEqual('/dev/mmcblk0p5', disk.RELEASE_ROOTFS.path)
    self.dut.CheckOutput.assert_called_with(['rootdev', '-s', '-d'])

    disk = partitions.Partitions(self.dut)
    self.dut.CheckOutput.return_value = '/dev/sda\n'

    self.assertEqual('/dev/sda1', disk.STATEFUL.path)
    self.assertEqual('/dev/sda2', disk.FACTORY_KERNEL.path)
    self.assertEqual('/dev/sda3', disk.FACTORY_ROOTFS.path)
    self.assertEqual('/dev/sda4', disk.RELEASE_KERNEL.path)
    self.assertEqual('/dev/sda5', disk.RELEASE_ROOTFS.path)
    self.dut.CheckOutput.assert_called_with(['rootdev', '-s', '-d'])

if __name__ == '__main__':
  unittest.main()
