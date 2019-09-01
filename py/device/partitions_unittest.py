#!/usr/bin/env python2
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit test for partitions module."""

import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import partitions
from cros.factory.device import types


class PartitionsTest(unittest.TestCase):
  """Unit test for Partition class."""

  def setUp(self):
    self.mox = mox.Mox()
    self.dut = self.mox.CreateMock(types.DeviceInterface)
    self.disk1 = partitions.Partitions(self.dut)
    self.disk2 = partitions.Partitions(self.dut)
    self.mox.StubOutWithMock(self.dut, 'CheckOutput')

  def testGetPartition(self):

    disk1 = self.disk1
    disk2 = self.disk2

    self.dut.CheckOutput(['rootdev', '-s', '-d']).AndReturn('/dev/mmcblk0\n')
    self.dut.CheckOutput(['rootdev', '-s', '-d']).AndReturn('/dev/sda\n')

    self.mox.ReplayAll()

    self.assertEquals('/dev/mmcblk0p1', disk1.STATEFUL.path)
    self.assertEquals('/dev/mmcblk0p2', disk1.FACTORY_KERNEL.path)
    self.assertEquals('/dev/mmcblk0p3', disk1.FACTORY_ROOTFS.path)
    self.assertEquals('/dev/mmcblk0p4', disk1.RELEASE_KERNEL.path)
    self.assertEquals('/dev/mmcblk0p5', disk1.RELEASE_ROOTFS.path)

    self.assertEquals('/dev/sda1', disk2.STATEFUL.path)
    self.assertEquals('/dev/sda2', disk2.FACTORY_KERNEL.path)
    self.assertEquals('/dev/sda3', disk2.FACTORY_ROOTFS.path)
    self.assertEquals('/dev/sda4', disk2.RELEASE_KERNEL.path)
    self.assertEquals('/dev/sda5', disk2.RELEASE_ROOTFS.path)

    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
