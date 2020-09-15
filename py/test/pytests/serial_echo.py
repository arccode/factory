# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks the communication between DUT and SMT test fixture.

SMT has a test fixture, which communicates with DUT via serial port.
This test is to make sure that the serial port works as expected.

It can also be used to send a command to the fixture before/after a test.

dargs:
  serial_param: a dict of parameters for a serial connection. Should contain
        'port'. For other parameters, like 'baudrate', 'bytesize', 'parity',
        'stopbits' and 'timeout', please refer pySerial documentation.
  send_recv: [send, recv]. send is a char for the DUT to send to
      a fixture. And recv is the expected one-char response from the fixture.
"""

import unittest

import serial

from cros.factory.test.utils import serial_utils
from cros.factory.utils.arg_utils import Arg

_SERIAL_TIMEOUT = 3


class SerialEchoTest(unittest.TestCase):
  ARGS = [
      Arg('serial_param', dict,
          'a dict of parameters for a serial connection. Should contain '
          '"port". For other parameters, like "baudrate", "bytesize", '
          '"parity", "stopbits" and "timeout", please refer pySerial '
          'documentation.'),
      Arg('send_recv', list,
          '[send, recv]. send is a char for the DUT to send to a '
          'fixture MCU. And recv is the expected one-char response from the '
          'fixture.',
          default=[chr(0xE0), chr(0xE1)])]

  def setUp(self):
    self._serial = None
    self._send = None
    self._recv = None

    if (len(self.args.send_recv) != 2 or
        not all(isinstance(a, str) for a in self.args.send_recv)):
      self.fail('Invalid dargs send_recv: %s' % str(self.args.send_recv))
    self._send = self.args.send_recv[0].encode('latin1')
    self._recv = self.args.send_recv[1].encode('latin1')

    # Will raise exception if OpenSerial fails.
    self._serial = serial_utils.OpenSerial(**self.args.serial_param)

  def tearDown(self):
    if self._serial:
      self._serial.close()

  def runTest(self):
    self.assertTrue(self._serial is not None, 'Invalid RS-232 connection.')
    try:
      self.assertEqual(1, self._serial.write(self._send), 'Write fail')
    except serial.SerialTimeoutException:
      self.fail('Write timeout')

    try:
      self.assertEqual(self._recv, self._serial.read(), 'Read fail')
    except serial.SerialTimeoutException:
      self.fail('Read timeout')
