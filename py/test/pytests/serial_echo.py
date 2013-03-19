# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks the communication between DUT and SMT test fixture.

SMT has a test fixture, which communicates with DUT via serial port.
This test is to make sure that the serial port works as expected.

dargs:
  serial_param: A parameter tuple of the target serial port:
      (port, baudrate, bytesize, parity, stopbits, timeout_secs).
      timeout_secs is used for both read and write timeout.
"""
import serial
import unittest

from cros.factory.test.args import Arg
from cros.factory.utils import serial_utils

_SERIAL_TIMEOUT = 3

class SerialEchoTest(unittest.TestCase):
  ARGS = [
    Arg('serial_param', tuple,
        'The parameter list of a serial connection we want to use.',
        default=('/dev/ttyUSB0', 19200, serial.EIGHTBITS, serial.PARITY_NONE,
                 serial.STOPBITS_ONE , _SERIAL_TIMEOUT)),
  ]

  def setUp(self):
    # Prepare fixture auto test if needed.
    self.serial = None
    try:
      self.serial = serial_utils.OpenSerial(self.args.serial_param)
    except serial.SerialException as e:
      self.fail(e)

  def tearDown(self):
    if self.serial:
      self.serial.close()

  def testEcho(self):
    echo = chr(0xE0)
    self.assertTrue(self.serial is not None, 'Invalid RS-232 connection.')
    self.assertEqual(1, self.serial.write(echo), 'Write fail.')
    self.assertEqual(echo, self.serial.read(), 'Read fail.')
