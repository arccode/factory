#!/usr/bin/python -u
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for serial_utils."""

import glob
import mox
import os
import serial
from serial import SerialException, SerialTimeoutException
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import serial_utils
from cros.factory.utils.serial_utils import SerialDevice

_DEFAULT_DRIVER = 'pl2303'
_DEFAULT_PORT = '/dev/ttyUSB0'
_SEND_RECEIVE_INTERVAL_SECS = 0.2
_RETRY_INTERVAL_SECS = 0.5
_COMMAND = 'Command'
_RESPONSE = '.'
_RECEIVE_SIZE = 1


class OpenSerialTest(unittest.TestCase):
  def setUp(self):
    self._mox = mox.Mox()

  def tearDown(self):
    self._mox.UnsetStubs()
    self._mox.VerifyAll()

  def testOpenSerial(self):
    # Sequence matters: create a serial mock then stub out serial.Serial.
    mock_serial = self._mox.CreateMock(serial.Serial)
    self._mox.StubOutWithMock(serial, 'Serial')
    serial.Serial(port=_DEFAULT_PORT, baudrate=19200).AndReturn(mock_serial)
    mock_serial.open()

    self._mox.ReplayAll()
    serial_utils.OpenSerial(port=_DEFAULT_PORT, baudrate=19200)

  def testOpenSerialNoPort(self):
    self.assertRaises(SerialException, serial_utils.OpenSerial)


class FindTtyByDriverTest(unittest.TestCase):
  def setUp(self):
    self._mox = mox.Mox()
    self._mox.StubOutWithMock(glob, 'glob')
    glob.glob('/dev/tty*').AndReturn(['/dev/ttyUSB0', '/dev/ttyUSB1'])
    self._mox.StubOutWithMock(os.path, 'realpath')

  def tearDown(self):
    self._mox.UnsetStubs()
    self._mox.VerifyAll()

  def testFindTtyByDriver(self):
    os.path.realpath('/sys/class/tty/ttyUSB0/device/driver').AndReturn(
        _DEFAULT_DRIVER)

    self._mox.ReplayAll()
    self.assertEquals(_DEFAULT_PORT,
                      serial_utils.FindTtyByDriver(_DEFAULT_DRIVER))

  def testFindTtyByDriverSecondPort(self):
    os.path.realpath('/sys/class/tty/ttyUSB0/device/driver').AndReturn('foo')
    os.path.realpath('/sys/class/tty/ttyUSB1/device/driver').AndReturn(
        _DEFAULT_DRIVER)

    self._mox.ReplayAll()
    self.assertEquals('/dev/ttyUSB1',
                      serial_utils.FindTtyByDriver(_DEFAULT_DRIVER))

  def testFindTtyByDriverNotFound(self):
    os.path.realpath('/sys/class/tty/ttyUSB0/device/driver').AndReturn('foo')
    os.path.realpath('/sys/class/tty/ttyUSB1/device/driver').AndReturn('bar')

    self._mox.ReplayAll()
    self.assertIsNone(serial_utils.FindTtyByDriver(_DEFAULT_DRIVER))


class SerialDeviceTest(unittest.TestCase):
  def setUp(self):
    self._mox = mox.Mox()
    self._serial = None  # defined in PrepareMockSerial

  def tearDown(self):
    self._mox.UnsetStubs()
    self._mox.VerifyAll()

  def PrepareMockSerial(self, driver):
    self._mox.StubOutWithMock(serial_utils, 'FindTtyByDriver')
    serial_utils.FindTtyByDriver(driver).AndReturn(_DEFAULT_PORT)
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    self._serial = self._mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(
        port=_DEFAULT_PORT, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
        timeout=0.5, writeTimeout=0.5).AndReturn(self._serial)

  def testCtor(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._serial.close()

    self._mox.ReplayAll()
    self.assertTrue(isinstance(SerialDevice(driver=_DEFAULT_DRIVER),
                               SerialDevice))

  def testCtorPortDriverMissing(self):
    self._mox.StubOutWithMock(serial_utils, 'FindTtyByDriver')
    serial_utils.FindTtyByDriver('UnknownDriver').AndReturn('')

    self._mox.ReplayAll()
    self.assertRaises(SerialException, SerialDevice,
                      driver='UnknownDriver')

  def testCtorDriverLookupFailure(self):
    self.assertRaises(SerialException, SerialDevice)

  def testCtorNoPortLookupIfPortSpecified(self):
    # FindTtyByDriver isn't called.
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    serial_utils.OpenSerial(
        port=_DEFAULT_PORT, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
        timeout=0.5, writeTimeout=0.5).AndReturn(None)

    self._mox.ReplayAll()
    self.assertTrue(
        isinstance(SerialDevice(driver='UnknownDriver', port=_DEFAULT_PORT),
                   SerialDevice))

  def testSend(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._serial.write(_COMMAND)
    self._serial.flush()
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    device.Send(_COMMAND)

  def testSendTimeout(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._serial.write(_COMMAND).AndRaise(SerialTimeoutException)
    self._serial.getWriteTimeout().AndReturn(0.5)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertRaises(SerialTimeoutException, device.Send, _COMMAND)

  def testReceive(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._serial.read(1).AndReturn('.')
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertEqual('.', device.Receive())

  def testReceiveTimeout(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._serial.read(1).AndReturn('')
    self._serial.getTimeout().AndReturn(0.5)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertRaises(SerialTimeoutException, device.Receive)

  def testReceiveShortageTimeout(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    # Requested 5 bytes, got only 4 bytes.
    self._serial.read(5).AndReturn('None')
    self._serial.getTimeout().AndReturn(0.5)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertRaises(SerialTimeoutException, device.Receive, 5)

  def testReceiveWhatsInBuffer(self):
    IN_BUFFER = 'InBuf'
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._serial.inWaiting().AndReturn(len(IN_BUFFER))
    self._serial.read(5).AndReturn(IN_BUFFER)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertEqual(IN_BUFFER, device.Receive(0))

  def MockForSendReceive(self):
    """Sets up mocks for SendReceive test.

    Stubs out time.sleep and FlushBuffer, Send and Receive in SerialDevice to
    facilitate unittesting SendReceive.
    """
    self._mox.StubOutWithMock(time, 'sleep')
    self._mox.StubOutWithMock(SerialDevice, 'FlushBuffer')
    self._mox.StubOutWithMock(SerialDevice, 'Send')
    self._mox.StubOutWithMock(SerialDevice, 'Receive')
    # pylint: disable=E1120
    SerialDevice.FlushBuffer()

  def testSendReceive(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self.MockForSendReceive()

    # pylint: disable=E1120
    SerialDevice.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    SerialDevice.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertEqual(_RESPONSE, device.SendReceive(_COMMAND))

  def testSendReceiveOverrideIntervalSecs(self):
    override_interval_secs = 1
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self.MockForSendReceive()

    # pylint: disable=E1120
    SerialDevice.Send(_COMMAND)
    time.sleep(override_interval_secs)
    SerialDevice.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertEqual(_RESPONSE,
                     device.SendReceive(_COMMAND,
                                        interval_secs=override_interval_secs))

  def testSendReceiveWriteTimeoutRetrySuccess(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self.MockForSendReceive()

    # Send timeout & retry.
    # pylint: disable=E1120
    SerialDevice.Send(_COMMAND).AndRaise(SerialTimeoutException)
    time.sleep(_RETRY_INTERVAL_SECS)
    # Retry okay.
    SerialDevice.FlushBuffer()
    SerialDevice.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    SerialDevice.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertEqual(_RESPONSE, device.SendReceive(_COMMAND, retry=1))

  def testSendReceiveReadTimeoutRetrySuccess(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self.MockForSendReceive()

    # Send okay.
    # pylint: disable=E1120
    SerialDevice.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    # Read timeout & retry.
    SerialDevice.Receive(_RECEIVE_SIZE).AndRaise(SerialTimeoutException)
    time.sleep(_RETRY_INTERVAL_SECS)
    # Retry okay.
    SerialDevice.FlushBuffer()
    SerialDevice.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    SerialDevice.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertEqual(_RESPONSE, device.SendReceive(_COMMAND, retry=1))

  def testSendRequestWriteTimeoutRetryFailure(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self.MockForSendReceive()

    # Send timeout & retry.
    # pylint: disable=E1120
    SerialDevice.Send(_COMMAND).AndRaise(SerialTimeoutException)
    time.sleep(_RETRY_INTERVAL_SECS)
    # Retry failed.
    SerialDevice.FlushBuffer()
    SerialDevice.Send(_COMMAND).AndRaise(SerialTimeoutException)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertRaises(SerialTimeoutException, device.SendReceive,
                      _COMMAND, retry=1)

  def testSendExpectReceive(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._mox.StubOutWithMock(SerialDevice, 'SendReceive')

    SerialDevice.SendReceive(
        _COMMAND, _RECEIVE_SIZE, retry=0, interval_secs=None,
        suppress_log=True).AndReturn(_RESPONSE)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertTrue(device.SendExpectReceive(_COMMAND, _RESPONSE))

  def testSendExpectReceiveMismatch(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._mox.StubOutWithMock(SerialDevice, 'SendReceive')

    SerialDevice.SendReceive(
        _COMMAND, _RECEIVE_SIZE, retry=0, interval_secs=None,
        suppress_log=True).AndReturn('x')
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertFalse(device.SendExpectReceive(_COMMAND, _RESPONSE))

  def testSendExpectReceiveTimeout(self):
    self.PrepareMockSerial(_DEFAULT_DRIVER)
    self._mox.StubOutWithMock(SerialDevice, 'SendReceive')

    SerialDevice.SendReceive(
        _COMMAND, _RECEIVE_SIZE, retry=0, interval_secs=None,
        suppress_log=True).AndRaise(SerialTimeoutException)
    self._serial.close()

    self._mox.ReplayAll()
    device = SerialDevice(driver=_DEFAULT_DRIVER)
    self.assertFalse(device.SendExpectReceive(_COMMAND, _RESPONSE))


if __name__ == '__main__':
  unittest.main()
