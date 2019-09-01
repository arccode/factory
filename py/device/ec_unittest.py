#!/usr/bin/env python2
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Embedded Controller."""

from __future__ import print_function

import textwrap
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import ec
from cros.factory.device import types


class EmbeddedControllerTest(unittest.TestCase):
  """Unittest for EmbeddedController."""

  _EC_VERSION_OUTPUT = textwrap.dedent("""
      RO version:    samus_v1.7.576-9648e39
      RW version:    samus_v1.7.688-22cf733
      Firmware copy: RW
      Build info:    samus_v1.7.688-22cf733 2015-07-16 11:31:57 @build291-m2""")

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.ec = ec.EmbeddedController(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetECVersion(self):
    self.board.CallOutput(
        ['mosys', 'ec', 'info', '-s', 'fw_version']).AndReturn(
            'link_v1.1.227-3b0e131')
    self.mox.ReplayAll()
    self.assertEquals(self.ec.GetECVersion(), 'link_v1.1.227-3b0e131')
    self.mox.VerifyAll()

  def testGetROVersion(self):
    self.board.CallOutput(['ectool', 'version']).AndReturn(
        self._EC_VERSION_OUTPUT)
    self.mox.ReplayAll()
    self.assertEquals(self.ec.GetROVersion(), 'samus_v1.7.576-9648e39')
    self.mox.VerifyAll()

  def testGetRWVersion(self):
    self.board.CallOutput(['ectool', 'version']).AndReturn(
        self._EC_VERSION_OUTPUT)
    self.mox.ReplayAll()
    self.assertEquals(self.ec.GetRWVersion(), 'samus_v1.7.688-22cf733')
    self.mox.VerifyAll()

  def testGetECConsoleLog(self):
    _MOCK_LOG = '\n'.join([
        '[hostcmd 0x20]',
        '[hostcmd 0x60]',
        '[charge state idle -> charge]'])

    self.board.CallOutput(['ectool', 'console']).AndReturn(_MOCK_LOG)
    self.mox.ReplayAll()
    self.assertEquals(self.ec.GetECConsoleLog(), _MOCK_LOG)
    self.mox.VerifyAll()

  def testGetECPanicInfo(self):
    _MOCK_PANIC = '\n'.join([
        'Saved panic data: (NEW)',
        '=== PROCESS EXCEPTION: 06 === xPSR: 21000000 ======',
        'r0 :00000000 r1 :0800a394 r2 :40013800 r3 :0000cdef',
        'r4 :00000000 r5 :00000011 r6 :20001aa0 r7 :00000000',
        'r8 :00000000 r9 :20001ab0 r10:00000000 r11:00000000',
        'r12:00000000 sp :20000fe0 lr :0800023d pc :08000242'])

    self.board.CallOutput(['ectool', 'panicinfo']).AndReturn(_MOCK_PANIC)
    self.mox.ReplayAll()
    self.assertEquals(self.ec.GetECPanicInfo(), _MOCK_PANIC)
    self.mox.VerifyAll()

  def testProbeEC(self):
    self.board.CallOutput(['ectool', 'hello']).AndReturn('EC says hello')
    self.mox.ReplayAll()
    self.ec.ProbeEC()
    self.mox.VerifyAll()

  def testProbeECFail(self):
    self.board.CallOutput(['ectool', 'hello']).AndReturn(
        'EC dooes not say hello')
    self.mox.ReplayAll()
    self.assertRaises(self.ec.Error, self.ec.ProbeEC)
    self.mox.VerifyAll()


  def testI2CRead(self):
    _MOCK_I2C_READ = 'Read from I2C port 0 at 0x12 offset 0x12 = 0xf912'
    self.board.CheckOutput(
        ['ectool', 'i2cread', '16', '0', '18', '18']).AndReturn(_MOCK_I2C_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.ec.I2CRead(0, 0x12, 0x12), 0xf912)
    self.mox.VerifyAll()

  def testI2CWrite(self):
    self.board.CheckCall(['ectool', 'i2cwrite', '16', '0', '18', '18', '0'])
    self.mox.ReplayAll()
    self.ec.I2CWrite(0, 0x12, 0x12, 0)
    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
