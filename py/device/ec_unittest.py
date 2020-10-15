#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Embedded Controller."""

import textwrap
import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import ec


class EmbeddedControllerTest(unittest.TestCase):
  """Unittest for EmbeddedController."""

  _EC_VERSION_OUTPUT = textwrap.dedent("""
      RO version:    samus_v1.7.576-9648e39
      RW version:    samus_v1.7.688-22cf733
      Firmware copy: RW
      Build info:    samus_v1.7.688-22cf733 2015-07-16 11:31:57 @build291-m2""")

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.ec = ec.EmbeddedController(self.board)

  def testGetECVersion(self):
    self.board.CallOutput.return_value = 'link_v1.1.227-3b0e131'

    self.assertEqual(self.ec.GetECVersion(), 'link_v1.1.227-3b0e131')
    self.board.CallOutput.assert_called_once_with(
        ['mosys', 'ec', 'info', '-s', 'fw_version'])

  def testGetROVersion(self):
    self.board.CallOutput.return_value = self._EC_VERSION_OUTPUT

    self.assertEqual(self.ec.GetROVersion(), 'samus_v1.7.576-9648e39')
    self.board.CallOutput.assert_called_once_with(['ectool', 'version'])

  def testGetRWVersion(self):
    self.board.CallOutput.return_value = self._EC_VERSION_OUTPUT

    self.assertEqual(self.ec.GetRWVersion(), 'samus_v1.7.688-22cf733')
    self.board.CallOutput.assert_called_once_with(['ectool', 'version'])

  def testGetECConsoleLog(self):
    _MOCK_LOG = '\n'.join([
        '[hostcmd 0x20]',
        '[hostcmd 0x60]',
        '[charge state idle -> charge]'])

    self.board.CallOutput.return_value = _MOCK_LOG

    self.assertEqual(self.ec.GetECConsoleLog(), _MOCK_LOG)
    self.board.CallOutput.assert_called_once_with(['ectool', 'console'])

  def testGetECPanicInfo(self):
    _MOCK_PANIC = '\n'.join([
        'Saved panic data: (NEW)',
        '=== PROCESS EXCEPTION: 06 === xPSR: 21000000 ======',
        'r0 :00000000 r1 :0800a394 r2 :40013800 r3 :0000cdef',
        'r4 :00000000 r5 :00000011 r6 :20001aa0 r7 :00000000',
        'r8 :00000000 r9 :20001ab0 r10:00000000 r11:00000000',
        'r12:00000000 sp :20000fe0 lr :0800023d pc :08000242'])

    self.board.CallOutput.return_value = _MOCK_PANIC

    self.assertEqual(self.ec.GetECPanicInfo(), _MOCK_PANIC)
    self.board.CallOutput.assert_called_once_with(['ectool', 'panicinfo'])

  def testProbeEC(self):
    self.board.CallOutput.return_value = 'EC says hello'

    self.ec.ProbeEC()
    self.board.CallOutput.assert_called_once_with(['ectool', 'hello'])

  def testProbeECFail(self):
    self.board.CallOutput.return_value = 'EC dooes not say hello'

    self.assertRaises(self.ec.Error, self.ec.ProbeEC)
    self.board.CallOutput.assert_called_once_with(['ectool', 'hello'])

  def testI2CRead(self):
    _MOCK_I2C_READ = 'Read from I2C port 0 at 0x12 offset 0x12 = 0xf912'
    self.board.CheckOutput.return_value = _MOCK_I2C_READ

    self.assertEqual(self.ec.I2CRead(0, 0x12, 0x12), 0xf912)
    self.board.CheckOutput.assert_called_once_with(
        ['ectool', 'i2cread', '16', '0', '18', '18'])

  def testI2CWrite(self):
    self.ec.I2CWrite(0, 0x12, 0x12, 0)
    self.board.CheckCall.assert_called_once_with(
        ['ectool', 'i2cwrite', '16', '0', '18', '18', '0'])

if __name__ == '__main__':
  unittest.main()
