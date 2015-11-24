#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import probe
from cros.factory.test.dut import vpd
from cros.factory.utils.type_utils import Obj


class ProbeRegionUnittest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(vpd.Partition, 'get')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testProbeVPD(self):
    vpd.Partition.get('region').AndReturn('us')
    self.mox.ReplayAll()

    result = probe._ProbeRegion()  # pylint: disable=W0212
    self.assertEquals([{'region_code': 'us'}], result)

    self.mox.VerifyAll()


class GetEMMC5FirmwareVersionUnittest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(probe, 'Shell')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testFirmwareVersionASCII(self):
    mock_stdout = """
[FIRMWARE_VERSION[261]]: 0x48
[FIRMWARE_VERSION[260]]: 0x47
[FIRMWARE_VERSION[259]]: 0x46
[FIRMWARE_VERSION[258]]: 0x45
[FIRMWARE_VERSION[257]]: 0x44
[FIRMWARE_VERSION[256]]: 0x43
[FIRMWARE_VERSION[255]]: 0x42
[FIRMWARE_VERSION[254]]: 0x41
"""
    probe.Shell('mmc extcsd read /dev/mmcblk0').AndReturn(
        Obj(stdout=mock_stdout))
    self.mox.ReplayAll()

    result = probe._GetEMMC5FirmwareVersion(  # pylint: disable=W0212
        '/sys/class/block/mmcblk0')
    self.assertEquals('4142434445464748 (ABCDEFGH)', result)
    self.mox.VerifyAll()

  def testFirmwareVersionASCIIStrips(self):
    mock_stdout = """
[FIRMWARE_VERSION[261]]: 0x20
[FIRMWARE_VERSION[260]]: 0x00
[FIRMWARE_VERSION[259]]: 0x46
[FIRMWARE_VERSION[258]]: 0x45
[FIRMWARE_VERSION[257]]: 0x44
[FIRMWARE_VERSION[256]]: 0x43
[FIRMWARE_VERSION[255]]: 0x42
[FIRMWARE_VERSION[254]]: 0x41
"""
    probe.Shell('mmc extcsd read /dev/mmcblk0').AndReturn(
        Obj(stdout=mock_stdout))
    self.mox.ReplayAll()

    result = probe._GetEMMC5FirmwareVersion(  # pylint: disable=W0212
        '/sys/class/block/mmcblk0')
    self.assertEquals('4142434445460020 (ABCDEF)', result)
    self.mox.VerifyAll()

  def testFirmwareVersionHex(self):
    mock_stdout = """
[FIRMWARE_VERSION[261]]: 0x00
[FIRMWARE_VERSION[260]]: 0x00
[FIRMWARE_VERSION[259]]: 0x00
[FIRMWARE_VERSION[258]]: 0x00
[FIRMWARE_VERSION[257]]: 0x00
[FIRMWARE_VERSION[256]]: 0x00
[FIRMWARE_VERSION[255]]: 0x00
[FIRMWARE_VERSION[254]]: 0x03
"""
    probe.Shell('mmc extcsd read /dev/mmcblk0').AndReturn(
        Obj(stdout=mock_stdout))
    self.mox.ReplayAll()

    result = probe._GetEMMC5FirmwareVersion(  # pylint: disable=W0212
        '/sys/class/block/mmcblk0')
    self.assertEquals('0300000000000000 (3)', result)
    self.mox.VerifyAll()

  def testFirmwareVersionNotFound(self):
    mock_stdout = """
No Firmware version.
"""
    probe.Shell('mmc extcsd read /dev/mmcblk0').AndReturn(
        Obj(stdout=mock_stdout))
    self.mox.ReplayAll()

    result = probe._GetEMMC5FirmwareVersion(  # pylint: disable=W0212
        '/sys/class/block/mmcblk0')
    self.assertTrue(result is None)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
