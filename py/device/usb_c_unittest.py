#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for USBTypeC."""

import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import usb_c


class MockUSBTypeC(usb_c.USBTypeC):
  ECTOOL_PD_ARGS = ['--interface=dev', '--dev=1']


class USBTypeCTest(unittest.TestCase):
  """Unittest for USBTypeC."""

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.usb_c = MockUSBTypeC(self.board)

  def testGetPDVersion(self):
    self.board.CallOutput.return_value = 'samus_pd_v1.1.2122-e1ff1a3'
    self.assertEqual('samus_pd_v1.1.2122-e1ff1a3', self.usb_c.GetPDVersion())
    self.board.CallOutput.assert_called_once_with(
        ['mosys', 'pd', 'info', '-s', 'fw_version'])

  def testGetPDStatusV0(self):
    self.board.CheckOutput.side_effect = [
        'Port C0 is enabled, Role:SRC Polarity:CC1 State:8',
        'Port C1 is disabled, Role:SNK Polarity:CC2 State:11']

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertEqual('SRC', status['role'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual(8, status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual(11, status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])

  def testGetPDStatusV1(self):
    self.board.CheckOutput.side_effect = [
        'Port C0 is enabled, Role:SRC UFP Polarity:CC1 State:SRC_READY',
        'Port C1 is disabled, Role:SNK DFP Polarity:CC2 State:SNK_DISCOVERY',
        'Port C1 is disabled, Role:SNK DFP Polarity:CC2 State:']

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertEqual('SRC', status['role'])
    self.assertEqual('UFP', status['datarole'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('SRC_READY', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual('SNK_DISCOVERY', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])
    self.board.CheckOutput.reset_mock()

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual('', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])

  def testGetPDStatusV1_1(self):
    self.board.CheckOutput.side_effect = [
        'Port C0 is enabled,connected, Role:SRC UFP Polarity:CC1 '
        'State:SRC_READY',
        'Port C1 is disabled,disconnected, Role:SNK DFP Polarity:CC2 '
        'State:SNK_DISCOVERY',
        'Port C1 is disabled,disconnected, Role:SNK DFP Polarity:CC2 State:']

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEqual('SRC', status['role'])
    self.assertEqual('UFP', status['datarole'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('SRC_READY', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual('SNK_DISCOVERY', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])
    self.board.CheckOutput.reset_mock()

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual('', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])

  def testGetPDStatusV1_2(self):
    self.board.CheckOutput.side_effect = [
        'Port C0: enabled, connected  State:SRC_READY\n'
        'Role:SRC UFP, Polarity:CC1',
        'Port C1: enabled, connected  State:SNK_DISCOVERY\n'
        'Role:SRC DFP VCONN, Polarity:CC1',
        'Port C1: disabled, disconnected  State:SNK_DISCONNECTED\n'
        'Role:SNK DFP, Polarity:CC2',
        'Port C1: disabled, disconnected  State:\n'
        'Role:SNK DFP, Polarity:CC2']

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEqual('SRC', status['role'])
    self.assertEqual('UFP', status['datarole'])
    self.assertEqual('', status['vconn'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('SRC_READY', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])

    status = self.usb_c.GetPDStatus(1)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEqual('SRC', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('VCONN', status['vconn'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('SNK_DISCOVERY', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])
    self.board.CheckOutput.reset_mock()

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('', status['vconn'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual('SNK_DISCONNECTED', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])
    self.board.CheckOutput.reset_mock()

    status = self.usb_c.GetPDStatus(1)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('', status['vconn'])
    self.assertEqual('CC2', status['polarity'])
    self.assertEqual('', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '1'])

  def testGetPDStatusV2(self):
    self.board.CheckOutput.side_effect = [
        'Port C0: disabled, disconnected  State:LowPowerMode\n'
        'Role:SNK UFP, Polarity:CC1\n'
        'CC State:None\n'
        'Cable type:Passive\n'
        'TBT Adapter type:Gen3\n'
        'Optical Cable:False\n'
        'Link LSRX Communication:Bi-directional\n'
        'TBT Cable Speed:UNKNOWN\n'
        'Rounded support: 3rd Gen rounded support',
        'Port C0: enabled, connected  State:Attached.SRC\n'
        'Role:SRC DFP VCONN, Polarity:CC1\n'
        'CC State:UFP attached\n'
        'DP pin mode:C\n'
        'Cable type:Passive\n'
        'TBT Adapter type:Gen3\n'
        'Optical Cable:False\n'
        'Link LSRX Communication:Bi-directional\n'
        'TBT Cable Speed:UNKNOWN\n'
        'Rounded support: 3rd Gen rounded support\n'
        'PD Partner Capabilities:',
        'Port C0: enabled, connected  State:Attached.SNK\n'
        'Role:SNK UFP, Polarity:CC1\n'
        'CC State:DFP attached\n'
        'Cable type:Passive\n'
        'TBT Adapter type:Gen3\n'
        'Optical Cable:False\n'
        'Link LSRX Communication:Bi-directional\n'
        'TBT Cable Speed:UNKNOWN\n'
        'Rounded support: 3rd Gen rounded support\n'
        'PD Partner Capabilities:\n'
        ' Unconstrained power\n']

    status = self.usb_c.GetPDStatus(0)
    self.assertFalse(status['enabled'])
    self.assertFalse(status['connected'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('UFP', status['datarole'])
    self.assertEqual('', status['vconn'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('LowPowerMode', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])
    self.board.CheckOutput.reset_mock()

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEqual('SRC', status['role'])
    self.assertEqual('DFP', status['datarole'])
    self.assertEqual('VCONN', status['vconn'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('Attached.SRC', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])
    self.board.CheckOutput.reset_mock()

    status = self.usb_c.GetPDStatus(0)
    self.assertTrue(status['enabled'])
    self.assertTrue(status['connected'])
    self.assertEqual('SNK', status['role'])
    self.assertEqual('UFP', status['datarole'])
    self.assertEqual('', status['vconn'])
    self.assertEqual('CC1', status['polarity'])
    self.assertEqual('Attached.SNK', status['state'])
    self.board.CheckOutput.assert_called_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0'])

  def testGetPDPowerStatus(self):
    self.board.CheckOutput.side_effect = [
        'Port 0: SNK Charger PD 14384mV / 2999mA, max 15000mV / 3000mA / '
        '45000mW\nPort 1: Disconnected']

    status = self.usb_c.GetPDPowerStatus()
    self.assertTrue(status[0])
    self.assertTrue(status[1])
    self.assertEqual(status[0]['role'], 'SNK')
    self.assertEqual(status[1]['role'], 'Disconnected')
    self.assertEqual(status[0]['type'], 'PD')
    self.assertEqual(status[0]['millivolt'], 14384)
    self.assertEqual(status[0]['milliampere'], 2999)
    self.assertEqual(status[0]['max_millivolt'], 15000)
    self.assertEqual(status[0]['max_milliampere'], 3000)
    self.assertEqual(status[0]['max_milliwatt'], 45000)
    self.board.CheckOutput.assert_called_once_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpdpower'])

  def testSetHPD(self):
    self.usb_c.SetHPD(0)
    self.board.CheckOutput.assert_called_once_with(
        ['ectool', '--interface=dev', '--dev=1', 'gpioset', 'USB_C0_DP_HPD',
         '1'])

  def testResetHPD(self):
    self.usb_c.ResetHPD(1)
    self.board.CheckOutput.assert_called_once_with(
        ['ectool', '--interface=dev', '--dev=1', 'gpioset', 'USB_C1_DP_HPD',
         '0'])

  def testSetPortFunction(self):
    self.usb_c.SetPortFunction(0, 'dp')
    self.board.CheckOutput.assert_called_once_with(
        ['ectool', '--interface=dev', '--dev=1', 'usbpd', '0', 'dp'])

  def testSetPortFunctionFail(self):
    self.assertRaises(device_types.DeviceException, self.usb_c.SetPortFunction,
                      0, 'display')

  def testResetPortFunction(self):
    check_output_calls = [
        mock.call(['ectool', '--interface=dev', '--dev=1', 'usbpd', '1',
                   'toggle']),
        mock.call(['ectool', '--interface=dev', '--dev=1', 'usbpd', '1',
                   'usb'])]

    self.usb_c.ResetPortFunction(1)
    self.assertEqual(self.board.CheckOutput.call_args_list, check_output_calls)

if __name__ == '__main__':
  unittest.main()
