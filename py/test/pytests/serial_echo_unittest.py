#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mox
from mox import IgnoreArg
import serial

import factory_common  # pylint: disable=unused-import
from cros.factory.test.pytests import serial_echo
from cros.factory.test.utils import serial_utils
from cros.factory.utils.arg_utils import Args


class SerialEchoUnittest(unittest.TestCase):

  def setUp(self):
    self._mox = mox.Mox()
    self._test_case = None
    self._test_result = None

  def tearDown(self):
    self._mox.UnsetStubs()
    self._mox.VerifyAll()

  def SetUpTestCase(self, args, test_case_name='testEcho'):
    self._test_case = serial_echo.SerialEchoTest(test_case_name)
    arg_spec = getattr(self._test_case, 'ARGS', [])
    if 'serial_param' not in args:
      args['serial_param'] = {'port': '/dev/ttyUSB0'}
    self._test_case.args = Args(*arg_spec).Parse(args)

  def RunTestCase(self):
    self._test_result = self._test_case.defaultTestResult()
    self._test_case.run(self._test_result)

  def HasError(self, expected_error, assert_message):
    self.assertEqual(1, len(self._test_result.errors), assert_message)
    self.assertTrue(self._test_result.errors[0][1].find(expected_error) != -1,
                    assert_message)

  def HasFailure(self, expected_failure, assert_message):
    self.assertEqual(1, len(self._test_result.failures), assert_message)
    self.assertTrue(
        self._test_result.failures[0][1].find(expected_failure) != -1,
        assert_message)

  def testSendRecvTupleTooLong(self):
    self.SetUpTestCase({'send_recv': ['tuple', 'too', 'long']})
    self.RunTestCase()
    self.HasError('Invalid dargs send_recv',
                  'Unable to detect invalid send_recv.')

  def testSendRecvTupleTooShort(self):
    self.SetUpTestCase({'send_recv': ['tuple_too_short']})
    self.RunTestCase()
    self.HasError('Invalid dargs send_recv',
                  'Unable to detect invalid send_recv.')

  def testSendRecvTupleNotStr(self):
    self.SetUpTestCase({'send_recv': [1, 2]})
    self.RunTestCase()
    self.HasError('Invalid dargs send_recv',
                  'Unable to detect invalid send_recv.')

  def testDefault(self):
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    mock_serial = self._mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(port=IgnoreArg()).AndReturn(mock_serial)

    mock_serial.write(chr(0xE0)).AndReturn(1)
    mock_serial.read().AndReturn(chr(0xE1))
    mock_serial.close()

    self._mox.ReplayAll()

    self.SetUpTestCase({})
    self.RunTestCase()
    self.assertEqual(0, len(self._test_result.errors))
    self.assertEqual(0, len(self._test_result.failures))

  def testOpenSerialFailed(self):
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    serial_utils.OpenSerial(port=IgnoreArg()).AndRaise(
        serial.SerialException('Failed to open serial port'))
    self._mox.ReplayAll()

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasError('Failed to open serial port',
                  'Unable to handle OpenSerial exception.')

  def testWriteFail(self):
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    mock_serial = self._mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(port=IgnoreArg()).AndReturn(mock_serial)

    mock_serial.write(chr(0xE0)).AndReturn(0)
    mock_serial.close()

    self._mox.ReplayAll()

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Write fail',
                    'Unable to handle write failure.')

  def testReadFail(self):
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    mock_serial = self._mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(port=IgnoreArg()).AndReturn(mock_serial)

    mock_serial.write(chr(0xE0)).AndReturn(1)
    mock_serial.read().AndReturn('0')
    mock_serial.close()

    self._mox.ReplayAll()

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Read fail',
                    'Unable to handle read failure.')

  def testWriteTimeout(self):
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    mock_serial = self._mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(port=IgnoreArg()).AndReturn(mock_serial)

    mock_serial.write(chr(0xE0)).AndRaise(serial.SerialTimeoutException)
    mock_serial.close()

    self._mox.ReplayAll()

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Write timeout',
                    'Unable to handle write timeout.')

  def testReadTimeout(self):
    self._mox.StubOutWithMock(serial_utils, 'OpenSerial')
    mock_serial = self._mox.CreateMock(serial.Serial)
    serial_utils.OpenSerial(port=IgnoreArg()).AndReturn(mock_serial)

    mock_serial.write(chr(0xE0)).AndReturn(1)
    mock_serial.read().AndRaise(serial.SerialTimeoutException)
    mock_serial.close()

    self._mox.ReplayAll()

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Read timeout',
                    'Unable to handle read timeout.')


if __name__ == '__main__':
  unittest.main()
