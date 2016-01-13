#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Embedded Controller."""

from __future__ import print_function

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import ec
from cros.factory.test.dut import board


class EmbeddedControllerTest(unittest.TestCase):
  """Unittest for EmbeddedController."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DUTBoard)
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

  def testGetPDVersion(self):
    self.board.CallOutput(
        ['mosys', 'pd', 'info', '-s', 'fw_version']).AndReturn(
            'samus_pd_v1.1.2122-e1ff1a3')
    self.mox.ReplayAll()
    self.assertEquals('samus_pd_v1.1.2122-e1ff1a3', self.ec.GetPDVersion())
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

  def testGetUSBPDStatusV0(self):
    self.board.CheckOutput(
        ['ectool', 'usbpd', '0']).AndReturn(
            'Port C0 is enabled, Role:SRC Polarity:CC1 State:8')
    self.board.CheckOutput(
        ['ectool', 'usbpd', '1']).AndReturn(
            'Port C1 is disabled, Role:SNK Polarity:CC2 State:11')

    self.mox.ReplayAll()

    status = self.ec.GetUSBPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals(8, status['state'])

    status = self.ec.GetUSBPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals(11, status['state'])

    self.mox.VerifyAll()

  def testGetUSBPDStatusV1(self):
    self.board.CheckOutput(
        ['ectool', 'usbpd', '0']).AndReturn(
            'Port C0 is enabled, Role:SRC UFP Polarity:CC1 State:SRC_READY')
    self.board.CheckOutput(
        ['ectool', 'usbpd', '1']).AndReturn(
            'Port C1 is disabled, Role:SNK DFP Polarity:CC2 State:SNK_DISCOVERY')

    self.mox.ReplayAll()

    status = self.ec.GetUSBPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('UFP', status['datarole'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SRC_READY', status['state'])

    status = self.ec.GetUSBPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals('SNK_DISCOVERY', status['state'])

    self.mox.VerifyAll()

  def testGetUSBPDStatusV1_1(self):
    self.board.CheckOutput(
        ['ectool', 'usbpd', '0']).AndReturn(
            'Port C0 is enabled,connected, Role:SRC UFP Polarity:CC1 '
            'State:SRC_READY')
    self.board.CheckOutput(
        ['ectool', 'usbpd', '1']).AndReturn(
            'Port C1 is disabled,disconnected, Role:SNK DFP Polarity:CC2 '
            'State:SNK_DISCOVERY')

    self.mox.ReplayAll()

    status = self.ec.GetUSBPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('UFP', status['datarole'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SRC_READY', status['state'])

    status = self.ec.GetUSBPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals('SNK_DISCOVERY', status['state'])

    self.mox.VerifyAll()

  def testGetUSBPDStatusV1_2(self):
    self.board.CheckOutput(
        ['ectool', 'usbpd', '0']).AndReturn(
            'Port C0: enabled, connected  State:SRC_READY\n'
            'Role:SRC UFP, '
            'Polarity:CC1')
    self.board.CheckOutput(
        ['ectool', 'usbpd', '1']).AndReturn(
            'Port C1: enabled, connected  State:SNK_DISCOVERY\n'
            'Role:SRC DFP VCONN, Polarity:CC1')
    self.board.CheckOutput(
        ['ectool', 'usbpd', '1']).AndReturn(
            'Port C1: disabled, disconnected  State:SNK_DISCONNECTED\n'
            'Role:SNK DFP, Polarity:CC2')

    self.mox.ReplayAll()

    status = self.ec.GetUSBPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('UFP', status['datarole'])
    self.assertEquals('', status['vconn'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SRC_READY', status['state'])

    status = self.ec.GetUSBPDStatus(1)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('VCONN', status['vconn'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SNK_DISCOVERY', status['state'])

    status = self.ec.GetUSBPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('', status['vconn'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals('SNK_DISCONNECTED', status['state'])

    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
