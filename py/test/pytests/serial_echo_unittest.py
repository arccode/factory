#!/usr/bin/env python3
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock
import serial

from cros.factory.test.pytests import serial_echo
from cros.factory.utils.arg_utils import Args


class SerialEchoUnittest(unittest.TestCase):

  def setUp(self):
    self._test_case = None
    self._test_result = None

  def SetUpTestCase(self, args, test_case_name='runTest'):
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
    self.HasFailure('Invalid dargs send_recv',
                    'Unable to detect invalid send_recv.')

  def testSendRecvTupleTooShort(self):
    self.SetUpTestCase({'send_recv': ['tuple_too_short']})
    self.RunTestCase()
    self.HasFailure('Invalid dargs send_recv',
                    'Unable to detect invalid send_recv.')

  def testSendRecvTupleNotStr(self):
    self.SetUpTestCase({'send_recv': [1, 2]})
    self.RunTestCase()
    self.HasFailure('Invalid dargs send_recv',
                    'Unable to detect invalid send_recv.')

  @mock.patch('cros.factory.test.utils.serial_utils.OpenSerial')
  def testDefault(self, open_serial_mock):
    mock_serial = mock.Mock(serial.Serial)
    mock_serial.write.return_value = 1
    mock_serial.read.return_value = b'\xE1'

    open_serial_mock.return_value = mock_serial

    self.SetUpTestCase({})
    self.RunTestCase()
    self.assertEqual(0, len(self._test_result.errors))
    self.assertEqual(0, len(self._test_result.failures))
    open_serial_mock.assert_called_once_with(port=mock.ANY)
    mock_serial.write.assert_called_once_with(b'\xE0')
    mock_serial.read.assert_called_once_with()
    mock_serial.close.assert_called_once_with()

  @mock.patch('cros.factory.test.utils.serial_utils.OpenSerial')
  def testOpenSerialFailed(self, open_serial_mock):
    open_serial_mock.side_effect = serial.SerialException(
        'Failed to open serial port')

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasError('Failed to open serial port',
                  'Unable to handle OpenSerial exception.')

  @mock.patch('cros.factory.test.utils.serial_utils.OpenSerial')
  def testWriteFail(self, open_serial_mock):
    mock_serial = mock.Mock(serial.Serial)
    mock_serial.write.return_value = 0

    open_serial_mock.return_value = mock_serial

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Write fail',
                    'Unable to handle write failure.')
    mock_serial.write.assert_called_once_with(b'\xE0')
    mock_serial.close.assert_called_once_with()

  @mock.patch('cros.factory.test.utils.serial_utils.OpenSerial')
  def testReadFail(self, open_serial_mock):
    mock_serial = mock.Mock(serial.Serial)
    mock_serial.write.return_value = 1
    mock_serial.read.return_value = '0'

    open_serial_mock.return_value = mock_serial

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Read fail',
                    'Unable to handle read failure.')
    mock_serial.write.assert_called_once_with(b'\xE0')
    mock_serial.read.assert_called_once_with()
    mock_serial.close.assert_called_once_with()

  @mock.patch('cros.factory.test.utils.serial_utils.OpenSerial')
  def testWriteTimeout(self, open_serial_mock):
    mock_serial = mock.Mock(serial.Serial)
    mock_serial.write.side_effect = serial.SerialTimeoutException

    open_serial_mock.return_value = mock_serial

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Write timeout',
                    'Unable to handle write timeout.')
    mock_serial.write.assert_called_once_with(b'\xE0')
    mock_serial.close.assert_called_once_with()

  @mock.patch('cros.factory.test.utils.serial_utils.OpenSerial')
  def testReadTimeout(self, open_serial_mock):
    mock_serial = mock.Mock(serial.Serial)
    mock_serial.write.return_value = 1
    mock_serial.read.side_effect = serial.SerialTimeoutException

    open_serial_mock.return_value = mock_serial

    self.SetUpTestCase({})
    self.RunTestCase()
    self.HasFailure('Read timeout',
                    'Unable to handle read timeout.')
    mock_serial.write.assert_called_once_with(b'\xE0')
    mock_serial.read.assert_called_once_with()
    mock_serial.close.assert_called_once_with()


if __name__ == '__main__':
  unittest.main()
