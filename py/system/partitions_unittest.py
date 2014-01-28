#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unit test for partitions module."""


import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.system import partitions


class PartitionsTest(unittest.TestCase):
  """Unit test for Partition class."""
  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(partitions, 'Spawn')

  def testGetPartition(self):
    class Stdout(object):
      """A dummy class to mock Spawn output."""
      def __init__(self, stdout_data):
        self.stdout_data = stdout_data

    for _ in xrange(5):
      partitions.Spawn(
          ['rootdev', '-d'], check_output=True).AndReturn(
        Stdout('/dev/mmcblk0'))

    for _ in xrange(5):
      partitions.Spawn(
          ['rootdev', '-d'], check_output=True).AndReturn(Stdout('/dev/sda'))

    self.mox.ReplayAll()

    self.assertEquals('/dev/mmcblk0p1', partitions.STATEFUL.path)
    self.assertEquals('/dev/mmcblk0p2', partitions.FACTORY_KERNEL.path)
    self.assertEquals('/dev/mmcblk0p3', partitions.FACTORY_ROOTFS.path)
    self.assertEquals('/dev/mmcblk0p4', partitions.RELEASE_KERNEL.path)
    self.assertEquals('/dev/mmcblk0p5', partitions.RELEASE_ROOTFS.path)

    self.assertEquals('/dev/sda1', partitions.STATEFUL.path)
    self.assertEquals('/dev/sda2', partitions.FACTORY_KERNEL.path)
    self.assertEquals('/dev/sda3', partitions.FACTORY_ROOTFS.path)
    self.assertEquals('/dev/sda4', partitions.RELEASE_KERNEL.path)
    self.assertEquals('/dev/sda5', partitions.RELEASE_ROOTFS.path)

    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
