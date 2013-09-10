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
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testOpenSerial(self):
    # Sequence matters: create a serial mock then stub out serial.Serial.
    mock_serial = self.mox.CreateMock(serial.Serial)
    self.mox.StubOutWithMock(serial, 'Serial')
    serial.Serial(port=_DEFAULT_PORT, baudrate=19200).AndReturn(mock_serial)
    mock_serial.open()

    self.mox.ReplayAll()
    serial_utils.OpenSerial(port=_DEFAULT_PORT, baudrate=19200)

  def testOpenSerialNoPort(self):
    self.assertRaises(SerialException, serial_utils.OpenSerial)


class FindTtyByDriverTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(glob, 'glob')
    glob.glob('/dev/tty*').AndReturn(['/dev/ttyUSB0', '/dev/ttyUSB1'])
    self.mox.StubOutWithMock(os.path, 'realpath')

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testFindTtyByDriver(self):
    os.path.realpath('/sys/class/tty/ttyUSB0/device/driver').AndReturn(
        _DEFAULT_DRIVER)

    self.mox.ReplayAll()
    self.assertEquals(_DEFAULT_PORT,
                      serial_utils.FindTtyByDriver(_DEFAULT_DRIVER))

  def testFindTtyByDriverSecondPort(self):
    os.path.realpath('/sys/class/tty/ttyUSB0/device/driver').AndReturn('foo')
    os.path.realpath('/sys/class/tty/ttyUSB1/device/driver').AndReturn(
        _DEFAULT_DRIVER)

    self.mox.ReplayAll()
    self.assertEquals('/dev/ttyUSB1',
                      serial_utils.FindTtyByDriver(_DEFAULT_DRIVER))

  def testFindTtyByDriverNotFound(self):
    os.path.realpath('/sys/class/tty/ttyUSB0/device/driver').AndReturn('foo')
    os.path.realpath('/sys/class/tty/ttyUSB1/device/driver').AndReturn('bar')

    self.mox.ReplayAll()
    self.assertIsNone(serial_utils.FindTtyByDriver(_DEFAULT_DRIVER))


class SerialDeviceCtorTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testCtor(self):
    device = SerialDevice()
    self.assertEqual(0.2, device.send_receive_interval_secs)
    self.assertEqual(0.5, device.retry_interval_secs)
    self.assertFalse(device.log)

  def testConnect(self):
    self.mox.StubOutWithMock(serial_utils, 'FindTtyByDriver')
    serial_utils.FindTtyByDriver(_DEFAULT_DRIVER).AndReturn(_DEFAULT_PORT)
    self.mox.StubOutWithMock(serial_utils, 'OpenSerial')
    mock_serial = self.mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(
        port=_DEFAULT_PORT, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
        timeout=0.5, writeTimeout=0.5).AndReturn(mock_serial)
    mock_serial.close()

    self.mox.ReplayAll()
    device = SerialDevice()
    device.Connect(driver=_DEFAULT_DRIVER)

  def testConnectPortDriverMissing(self):
    device = SerialDevice()
    self.assertRaises(SerialException, device.Connect)

  def testConnectDriverLookupFailure(self):
    self.mox.StubOutWithMock(serial_utils, 'FindTtyByDriver')
    serial_utils.FindTtyByDriver('UnknownDriver').AndReturn('')

    self.mox.ReplayAll()
    device = SerialDevice()
    self.assertRaises(SerialException, device.Connect,
                      driver='UnknownDriver')

  def testCtorNoPortLookupIfPortSpecified(self):
    # FindTtyByDriver isn't called.
    self.mox.StubOutWithMock(serial_utils, 'OpenSerial')
    serial_utils.OpenSerial(
        port=_DEFAULT_PORT, baudrate=9600, bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
        timeout=0.5, writeTimeout=0.5).AndReturn(None)

    self.mox.ReplayAll()
    device = SerialDevice()
    device.Connect(driver='UnknownDriver', port=_DEFAULT_PORT)

class SerialDeviceSendAndReceiveTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.device = SerialDevice()

    # Mock Serial and inject it.
    self.mock_serial = self.mox.CreateMock(serial.Serial)
    self.device._serial = self.mock_serial

  def tearDown(self):
    del self.device
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testSend(self):
    self.mock_serial.write(_COMMAND)
    self.mock_serial.flush()
    self.mock_serial.close()

    self.mox.ReplayAll()
    self.device.Send(_COMMAND)

  def testSendTimeout(self):
    self.mock_serial.write(_COMMAND).AndRaise(SerialTimeoutException)
    self.mock_serial.getWriteTimeout().AndReturn(0.5)
    self.mock_serial.close()

    self.mox.ReplayAll()
    self.assertRaises(SerialTimeoutException, self.device.Send, _COMMAND)

  def testReceive(self):
    self.mock_serial.read(1).AndReturn('.')
    self.mock_serial.close()

    self.mox.ReplayAll()
    self.assertEqual('.', self.device.Receive())

  def testReceiveTimeout(self):
    self.mock_serial.read(1).AndReturn('')
    self.mock_serial.getTimeout().AndReturn(0.5)
    self.mock_serial.close()

    self.mox.ReplayAll()
    self.assertRaises(SerialTimeoutException, self.device.Receive)

  def testReceiveShortageTimeout(self):
    # Requested 5 bytes, got only 4 bytes.
    self.mock_serial.read(5).AndReturn('None')
    self.mock_serial.getTimeout().AndReturn(0.5)
    self.mock_serial.close()

    self.mox.ReplayAll()
    self.assertRaises(SerialTimeoutException, self.device.Receive, 5)

  def testReceiveWhatsInBuffer(self):
    IN_BUFFER = 'InBuf'
    self.mock_serial.inWaiting().AndReturn(len(IN_BUFFER))
    self.mock_serial.read(5).AndReturn(IN_BUFFER)
    self.mock_serial.close()

    self.mox.ReplayAll()
    self.assertEqual(IN_BUFFER, self.device.Receive(0))

class SerialDeviceSendReceiveTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.device = SerialDevice()

    # Mock methods to facilitate SendReceive testing.
    self.mox.StubOutWithMock(time, 'sleep')
    self.mox.StubOutWithMock(self.device, 'FlushBuffer')
    self.mox.StubOutWithMock(self.device, 'Send')
    self.mox.StubOutWithMock(self.device, 'Receive')
    self.device.FlushBuffer()

  def tearDown(self):
    del self.device
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testSendReceive(self):
    self.device.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    self.device.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)

    self.mox.ReplayAll()
    self.assertEqual(_RESPONSE, self.device.SendReceive(_COMMAND))

  def testSendReceiveOverrideIntervalSecs(self):
    override_interval_secs = 1
    self.device.Send(_COMMAND)
    time.sleep(override_interval_secs)
    self.device.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)

    self.mox.ReplayAll()
    self.assertEqual(
        _RESPONSE,
        self.device.SendReceive(_COMMAND,
                                interval_secs=override_interval_secs))

  def testSendReceiveWriteTimeoutRetrySuccess(self):
    # Send timeout & retry.
    self.device.Send(_COMMAND).AndRaise(SerialTimeoutException)
    time.sleep(_RETRY_INTERVAL_SECS)
    # Retry okay.
    self.device.FlushBuffer()
    self.device.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    self.device.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)

    self.mox.ReplayAll()
    self.assertEqual(_RESPONSE, self.device.SendReceive(_COMMAND, retry=1))

  def testSendReceiveReadTimeoutRetrySuccess(self):
    # Send okay.
    self.device.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    # Read timeout & retry.
    self.device.Receive(_RECEIVE_SIZE).AndRaise(SerialTimeoutException)
    time.sleep(_RETRY_INTERVAL_SECS)
    # Retry okay.
    self.device.FlushBuffer()
    self.device.Send(_COMMAND)
    time.sleep(_SEND_RECEIVE_INTERVAL_SECS)
    self.device.Receive(_RECEIVE_SIZE).AndReturn(_RESPONSE)

    self.mox.ReplayAll()
    self.assertEqual(_RESPONSE, self.device.SendReceive(_COMMAND, retry=1))

  def testSendRequestWriteTimeoutRetryFailure(self):
    # Send timeout & retry.
    self.device.Send(_COMMAND).AndRaise(SerialTimeoutException)
    time.sleep(_RETRY_INTERVAL_SECS)
    # Retry failed.
    self.device.FlushBuffer()
    self.device.Send(_COMMAND).AndRaise(SerialTimeoutException)

    self.mox.ReplayAll()
    self.assertRaises(SerialTimeoutException, self.device.SendReceive,
                      _COMMAND, retry=1)

class SerialDeviceSendExpectReceiveTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.device = SerialDevice()

    # Mock methods to facilitate SendExpectReceive testing.
    self.mox.StubOutWithMock(self.device, 'SendReceive')

  def tearDown(self):
    del self.device
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testSendExpectReceive(self):
    self.device.SendReceive(
        _COMMAND, _RECEIVE_SIZE, retry=0, interval_secs=None,
        suppress_log=True).AndReturn(_RESPONSE)

    self.mox.ReplayAll()
    self.assertTrue(self.device.SendExpectReceive(_COMMAND, _RESPONSE))

  def testSendExpectReceiveMismatch(self):
    self.device.SendReceive(
        _COMMAND, _RECEIVE_SIZE, retry=0, interval_secs=None,
        suppress_log=True).AndReturn('x')

    self.mox.ReplayAll()
    self.assertFalse(self.device.SendExpectReceive(_COMMAND, _RESPONSE))

  def testSendExpectReceiveTimeout(self):
    self.device.SendReceive(
        _COMMAND, _RECEIVE_SIZE, retry=0, interval_secs=None,
        suppress_log=True).AndRaise(SerialTimeoutException)

    self.mox.ReplayAll()
    self.assertFalse(self.device.SendExpectReceive(_COMMAND, _RESPONSE))


if __name__ == '__main__':
  unittest.main()
