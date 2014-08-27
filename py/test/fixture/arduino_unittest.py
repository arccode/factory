#!/usr/bin/python -u
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for serial_utils."""

import mox
import serial
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.fixture.arduino import ArduinoController
from cros.factory.test.serial_utils import SerialDevice

_DEFAULT_DRIVER = 'cdc_acm'
_DEFAULT_READY_DELAY_SECS = 2.0

# pylint: disable=E1120
class ArduinoControllerTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.device = ArduinoController()

  def tearDown(self):
    del self.device
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def StubOutForConnect(self):
    self.mox.StubOutWithMock(SerialDevice, 'Connect')
    self.mox.StubOutWithMock(time, 'sleep')
    self.mox.StubOutWithMock(self.device, 'Ping')

  def testConnectDefault(self):
    self.StubOutForConnect()
    SerialDevice.Connect(driver=_DEFAULT_DRIVER)
    time.sleep(_DEFAULT_READY_DELAY_SECS)
    self.device.Ping().AndReturn(True)

    self.mox.ReplayAll()
    self.device.Connect()

  def testCustomReadyDelay(self):
    ready_delay_secs = 0.5
    self.device = ArduinoController(ready_delay_secs=ready_delay_secs)
    self.StubOutForConnect()
    SerialDevice.Connect(driver=_DEFAULT_DRIVER)
    time.sleep(ready_delay_secs)
    self.device.Ping().AndReturn(True)

    self.mox.ReplayAll()
    self.device.Connect()

  def testCustomDriver(self):
    custom_driver = 'CustomDriver'
    self.StubOutForConnect()
    SerialDevice.Connect(driver=custom_driver)
    time.sleep(_DEFAULT_READY_DELAY_SECS)
    self.device.Ping().AndReturn(True)

    self.mox.ReplayAll()
    self.device.Connect(driver=custom_driver)

  def testConnectPingFailed(self):
    self.StubOutForConnect()
    SerialDevice.Connect(driver=_DEFAULT_DRIVER)
    time.sleep(_DEFAULT_READY_DELAY_SECS)
    self.device.Ping().AndReturn(False)

    self.mox.ReplayAll()
    self.assertRaises(serial.SerialException, self.device.Connect)

  def testPing(self):
    self.mox.StubOutWithMock(self.device, 'SendExpectReceive')
    self.device.SendExpectReceive(chr(1), chr(1), retry=0).AndReturn(True)
    self.device.SendExpectReceive(chr(2), chr(2)).AndReturn(True)
    self.device.SendExpectReceive(chr(3), chr(3)).AndReturn(True)

    self.mox.ReplayAll()
    self.assertTrue(self.device.Ping())

  def testPingFail(self):
    self.mox.StubOutWithMock(self.device, 'SendExpectReceive')
    self.device.SendExpectReceive(chr(1), chr(1), retry=0).AndReturn(True)
    self.device.SendExpectReceive(chr(2), chr(2)).AndReturn(False)

    self.mox.ReplayAll()
    self.assertFalse(self.device.Ping())

  def testReset(self):
    mock_serial = self.mox.CreateMock(serial.Serial)
    self.mox.StubOutWithMock(time, 'sleep')
    self.device._serial = mock_serial
    mock_serial.setDTR(False)
    time.sleep(0.05)
    mock_serial.setDTR(True)
    time.sleep(_DEFAULT_READY_DELAY_SECS)
    mock_serial.close()

    self.mox.ReplayAll()
    self.device.Reset()

  def testResetNoWait(self):
    mock_serial = self.mox.CreateMock(serial.Serial)
    self.mox.StubOutWithMock(time, 'sleep')
    self.device._serial = mock_serial
    mock_serial.setDTR(False)
    time.sleep(0.05)
    mock_serial.setDTR(True)
    mock_serial.close()

    self.mox.ReplayAll()
    self.device.Reset(wait_ready=False)


if __name__ == '__main__':
  unittest.main()

