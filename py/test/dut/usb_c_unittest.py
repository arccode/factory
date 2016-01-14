#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for USBTypeC."""

from __future__ import print_function

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.dut import board
from cros.factory.test.dut import usb_c


class MockUSBTypeC(usb_c.USBTypeC):
  ECTOOL_PD_ARGS = ['--interface=dev', '--dev=1']


class USBTypeCTest(unittest.TestCase):
  """Unittest for USBTypeC."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DUTBoard)
    self.usb_c = MockUSBTypeC(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetPDVersion(self):
    self.board.CallOutput(
        ['mosys', 'pd', 'info', '-s', 'fw_version']).AndReturn(
            'samus_pd_v1.1.2122-e1ff1a3')
    self.mox.ReplayAll()
    self.assertEquals('samus_pd_v1.1.2122-e1ff1a3', self.usb_c.GetPDVersion())
    self.mox.VerifyAll()

  def testGetPDStatusV0(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0']).AndReturn(
            'Port C0 is enabled, Role:SRC Polarity:CC1 State:8')
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1']).AndReturn(
            'Port C1 is disabled, Role:SNK Polarity:CC2 State:11')

    self.mox.ReplayAll()

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals(8, status['state'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals(11, status['state'])

    self.mox.VerifyAll()

  def testGetPDStatusV1(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0']).AndReturn(
            'Port C0 is enabled, Role:SRC UFP Polarity:CC1 State:SRC_READY')
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1']).AndReturn(
            'Port C1 is disabled, Role:SNK DFP Polarity:CC2 State:SNK_DISCOVERY')

    self.mox.ReplayAll()

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('UFP', status['datarole'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SRC_READY', status['state'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals('SNK_DISCOVERY', status['state'])

    self.mox.VerifyAll()

  def testGetPDStatusV1_1(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0']).AndReturn(
            'Port C0 is enabled,connected, Role:SRC UFP Polarity:CC1 '
            'State:SRC_READY')
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1']).AndReturn(
            'Port C1 is disabled,disconnected, Role:SNK DFP Polarity:CC2 '
            'State:SNK_DISCOVERY')

    self.mox.ReplayAll()

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('UFP', status['datarole'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SRC_READY', status['state'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals('SNK_DISCOVERY', status['state'])

    self.mox.VerifyAll()

  def testGetPDStatusV1_2(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0']).AndReturn(
            'Port C0: enabled, connected  State:SRC_READY\n'
            'Role:SRC UFP, '
            'Polarity:CC1')
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1']).AndReturn(
            'Port C1: enabled, connected  State:SNK_DISCOVERY\n'
            'Role:SRC DFP VCONN, Polarity:CC1')
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1']).AndReturn(
            'Port C1: disabled, disconnected  State:SNK_DISCONNECTED\n'
            'Role:SNK DFP, Polarity:CC2')

    self.mox.ReplayAll()

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('UFP', status['datarole'])
    self.assertEquals('', status['vconn'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SRC_READY', status['state'])

    status = self.usb_c.GetPDStatus(1)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEquals('SRC', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('VCONN', status['vconn'])
    self.assertEquals('CC1', status['polarity'])
    self.assertEquals('SNK_DISCOVERY', status['state'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEquals('SNK', status['role'])
    self.assertEquals('DFP', status['datarole'])
    self.assertEquals('', status['vconn'])
    self.assertEquals('CC2', status['polarity'])
    self.assertEquals('SNK_DISCONNECTED', status['state'])

    self.mox.VerifyAll()

  def testGetPDPowerStatus(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'usbpdpower']).AndReturn(
            'Port 0: SNK Charger PD 14384mV / 2999mA, max 15000mV / 3000mA / 45000mW\n'
            'Port 1: Disconnected')

    self.mox.ReplayAll()

    status = self.usb_c.GetPDPowerStatus()
    self.assertTrue(status[0])
    self.assertTrue(status[1])
    self.assertEquals(status[0]['role'], 'SNK')
    self.assertEquals(status[1]['role'], 'Disconnected')
    self.assertEquals(status[0]['type'], 'PD')
    self.assertEquals(status[0]['millivolt'], 14384)
    self.assertEquals(status[0]['milliampere'], 2999)
    self.assertEquals(status[0]['max_millivolt'], 15000)
    self.assertEquals(status[0]['max_milliampere'], 3000)
    self.assertEquals(status[0]['max_milliwatt'], 45000)

    self.mox.VerifyAll()

  def testSetHPD(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'gpioset', 'USB_C0_DP_HPD', '1'])
    self.mox.ReplayAll()
    self.usb_c.SetHPD(0)
    self.mox.VerifyAll()

  def testResetHPD(self):
    self.board.CheckOutput(
        ['ectool', '--interface=dev', '--dev=1', 'gpioset', 'USB_C1_DP_HPD', '0'])
    self.mox.ReplayAll()
    self.usb_c.ResetHPD(1)
    self.mox.VerifyAll()

  def testSetPortFunction(self):
    self.board.CheckOutput(['ectool', '--interface=dev', '--dev=1', 'usbpd', '0', 'dp'])
    self.mox.ReplayAll()
    self.usb_c.SetPortFunction(0, 'dp')
    self.mox.VerifyAll()

  def testSetPortFunctionFail(self):
    self.assertRaises(component.DUTException, self.usb_c.SetPortFunction, 0, 'display')

  def testResetPortFunction(self):
    self.board.CheckOutput(['ectool', '--interface=dev', '--dev=1', 'usbpd', '1', 'toggle'])
    self.board.CheckOutput(['ectool', '--interface=dev', '--dev=1', 'usbpd', '1', 'usb'])
    self.mox.ReplayAll()
    self.usb_c.ResetPortFunction(1)
    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
