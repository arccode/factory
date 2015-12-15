#!/usr/bin/python -u
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for SystemInfo."""


import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test.dut import info as info_module
from cros.factory.system import partitions

MOCK_RELEASE_IMAGE_LSB_RELEASE = ('GOOGLE_RELEASE=5264.0.0\n'
                                  'CHROMEOS_RELEASE_TRACK=canary-channel\n')


class SystemInfoTest(unittest.TestCase):
  """Unittest for SystemInfo."""

  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def runTest(self):

    self.mox.StubOutWithMock(partitions, 'GetRootDev')
    partitions.GetRootDev().AndReturn('/dev/sda')
    self.mox.StubOutWithMock(info_module, 'MountDeviceAndReadFile')
    info_module.MountDeviceAndReadFile(
        '/dev/sda5', '/etc/lsb-release').AndReturn(
            MOCK_RELEASE_IMAGE_LSB_RELEASE)

    self.mox.ReplayAll()

    info = info_module.SystemInfo(dut.Create())
    self.assertEquals('5264.0.0', info.release_image_version)
    self.assertEquals('canary-channel', info.release_image_channel)
    # The cached release image version will be used in the second time.
    self.assertEquals('5264.0.0', info.release_image_version)
    self.assertEquals('canary-channel', info.release_image_channel)

    self.mox.VerifyAll()

if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(filename)s:%(lineno)d:%(levelname)s:%(message)s',
      level=logging.DEBUG)
  unittest.main()
