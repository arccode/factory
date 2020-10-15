#!/usr/bin/env python3
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for serial_utils."""

import unittest
from unittest import mock

import serial

from cros.factory.test.fixture import arduino

_DEFAULT_DRIVER = 'cdc_acm'
_DEFAULT_READY_DELAY_SECS = 2.0

# pylint: disable=no-value-for-parameter


class ArduinoControllerTest(unittest.TestCase):

  def setUp(self):
    self.device = arduino.ArduinoController()

  def tearDown(self):
    del self.device

  @mock.patch('time.sleep')
  @mock.patch('cros.factory.test.utils.serial_utils.SerialDevice.Connect')
  def testConnectDefault(self, connect_mock, sleep_mock):
    self.device.Ping = mock.Mock(return_value=True)

    self.device.Connect()

    connect_mock.assert_called_once_with(driver=_DEFAULT_DRIVER)
    sleep_mock.assert_called_once_with(_DEFAULT_READY_DELAY_SECS)
    self.device.Ping.assert_called_once_with()

  @mock.patch('time.sleep')
  @mock.patch('cros.factory.test.utils.serial_utils.SerialDevice.Connect')
  def testCustomReadyDelay(self, connect_mock, sleep_mock):
    ready_delay_secs = 0.5
    self.device = arduino.ArduinoController(ready_delay_secs=ready_delay_secs)
    self.device.Ping = mock.Mock(return_value=True)

    self.device.Connect()

    connect_mock.assert_called_once_with(driver=_DEFAULT_DRIVER)
    sleep_mock.assert_called_once_with(ready_delay_secs)
    self.device.Ping.assert_called_once_with()

  @mock.patch('time.sleep')
  @mock.patch('cros.factory.test.utils.serial_utils.SerialDevice.Connect')
  def testCustomDriver(self, connect_mock, sleep_mock):
    custom_driver = 'CustomDriver'
    self.device.Ping = mock.Mock(return_value=True)

    self.device.Connect(driver=custom_driver)

    connect_mock.assert_called_once_with(driver=custom_driver)
    sleep_mock.assert_called_once_with(_DEFAULT_READY_DELAY_SECS)
    self.device.Ping.assert_called_once_with()

  @mock.patch('time.sleep')
  @mock.patch('cros.factory.test.utils.serial_utils.SerialDevice.Connect')
  def testConnectPingFailed(self, connect_mock, sleep_mock):
    self.device.Ping = mock.Mock(return_value=False)

    self.assertRaises(serial.SerialException, self.device.Connect)

    connect_mock.assert_called_once_with(driver=_DEFAULT_DRIVER)
    sleep_mock.assert_called_once_with(_DEFAULT_READY_DELAY_SECS)
    self.device.Ping.assert_called_once_with()

  def testPing(self):
    self.device.SendExpectReceive = mock.Mock(side_effect=[True, True, True])
    send_expect_receive_calls = [
        mock.call(chr(1), chr(1), retry=0),
        mock.call(chr(2), chr(2)),
        mock.call(chr(3), chr(3))]

    self.assertTrue(self.device.Ping())

    self.assertEqual(self.device.SendExpectReceive.call_args_list,
                     send_expect_receive_calls)

  def testPingFail(self):
    self.device.SendExpectReceive = mock.Mock(side_effect=[True, False])
    send_expect_receive_calls = [
        mock.call(chr(1), chr(1), retry=0),
        mock.call(chr(2), chr(2))]

    self.assertFalse(self.device.Ping())

    self.assertEqual(self.device.SendExpectReceive.call_args_list,
                     send_expect_receive_calls)

  @mock.patch('time.sleep')
  def testReset(self, sleep_mock):
    serial_mock = mock.Mock(serial.Serial)
    self.device._serial = serial_mock  # pylint: disable=protected-access
    serial_setDTR_calls = [mock.call(False), mock.call(True)]
    sleep_calls = [mock.call(0.05), mock.call(_DEFAULT_READY_DELAY_SECS)]

    self.device.Reset()

    self.assertEqual(serial_mock.setDTR.call_args_list, serial_setDTR_calls)
    self.assertEqual(sleep_mock.call_args_list, sleep_calls)

  @mock.patch('time.sleep')
  def testResetNoWait(self, sleep_mock):
    serial_mock = mock.Mock(serial.Serial)
    self.device._serial = serial_mock  # pylint: disable=protected-access
    serial_setDTR_calls = [mock.call(False), mock.call(True)]

    self.device.Reset(wait_ready=False)

    self.assertEqual(serial_mock.setDTR.call_args_list, serial_setDTR_calls)
    sleep_mock.assert_called_once_with(0.05)


if __name__ == '__main__':
  unittest.main()
