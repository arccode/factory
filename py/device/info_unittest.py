#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for SystemInfo."""


import logging
import unittest
from unittest import mock

from cros.factory.device import info as info_module

MOCK_RELEASE_IMAGE_LSB_RELEASE = ('GOOGLE_RELEASE=5264.0.0\n'
                                  'CHROMEOS_RELEASE_TRACK=canary-channel\n')


class SystemInfoTest(unittest.TestCase):
  """Unittest for SystemInfo."""

  @mock.patch('cros.factory.device.info.MountDeviceAndReadFile')
  def runTest(self, mount_and_read_mock):
    dut = mock.MagicMock()
    dut.partitions.RELEASE_ROOTFS.path = '/dev/sda5'
    mount_and_read_mock.return_value = MOCK_RELEASE_IMAGE_LSB_RELEASE

    info = info_module.SystemInfo(dut)
    self.assertEqual('5264.0.0', info.release_image_version)
    self.assertEqual('canary-channel', info.release_image_channel)
    # The cached release image version will be used in the second time.
    self.assertEqual('5264.0.0', info.release_image_version)
    self.assertEqual('canary-channel', info.release_image_channel)

    mount_and_read_mock.assert_called_once_with('/dev/sda5', '/etc/lsb-release',
                                                dut=dut)

if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(filename)s:%(lineno)d:%(levelname)s:%(message)s',
      level=logging.DEBUG)
  unittest.main()
