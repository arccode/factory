#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import probe
from cros.factory.utils.type_utils import Obj


class ProbeRegionUnittest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(probe, 'ReadVpd')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testProbeVPD(self):
    probe.ReadVpd('RO_VPD', None).AndReturn({'region': 'us'})
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


# pylint: disable=protected-access
class ProbePCIUnittest(unittest.TestCase):
  """Test the probe._ReadSysfsPciFields function."""
  def setUp(self):
    self.mock_sysfs = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isdir(self.mock_sysfs):
      shutil.rmtree(self.mock_sysfs)

  def testPCI(self):
    with open(os.path.join(self.mock_sysfs, 'vendor'), 'w') as f:
      f.write('0x0123')
    with open(os.path.join(self.mock_sysfs, 'device'), 'w') as f:
      f.write('0xabcd')
    with open(os.path.join(self.mock_sysfs, 'config'), 'wb') as f:
      # Write revision id 'ef' in the 0x08 bit
      f.write('\x00' * 0x08)
      f.write('\xef')

    expected_result = {
        'vendor': '0x0123',
        'device': '0xabcd',
        'revision_id': '0xef',
        'compact_str': '0123:abcd (rev ef)'}
    result = probe._ReadSysfsPciFields(self.mock_sysfs)
    self.assertEquals(result, expected_result)

  def testPCIWithoutConfig(self):
    with open(os.path.join(self.mock_sysfs, 'vendor'), 'w') as f:
      f.write('0x0123')
    with open(os.path.join(self.mock_sysfs, 'device'), 'w') as f:
      f.write('0xabcd')

    result = probe._ReadSysfsPciFields(self.mock_sysfs)
    self.assertEquals(result, None)

  def testPCIWithWrongSysfs(self):
    result = probe._ReadSysfsPciFields(self.mock_sysfs)
    self.assertEquals(result, None)


class UtilFunctionsTest(unittest.TestCase):
  def testRemoveAutoSuffix(self):
    probe_value_map = {
        'audio_codec': {
            'COMPACT_STR': 'hdmi-audio-codec.1.auto'}}
    expected_result = {
        'audio_codec': {
            'COMPACT_STR': 'hdmi-audio-codec'}}
    self.assertEquals(probe.RemoveAutoSuffix(probe_value_map), expected_result)

    probe_value_map = {
        'audio_codec': [
            {'COMPACT_STR': 'hdmi-audio-codec.1.auto'},
            {'COMPACT_STR': 'foo.20.auto'}]}
    expected_result = {
        'audio_codec': [
            {'COMPACT_STR': 'hdmi-audio-codec'},
            {'COMPACT_STR': 'foo'}]}
    self.assertEquals(probe.RemoveAutoSuffix(probe_value_map), expected_result)


if __name__ == '__main__':
  unittest.main()
