# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper for talking with a tty modem."""

import serial
import logging

import factory_common  # pylint: disable=W0611
from cros.factory.common import Error


class Modem(object):
  def __init__(self, port, timeout=2,
               cancel_echo=False, disable_operation=False):
    """Initiates a modem serial port communication.

    Args:
      port: the relative port path starts from '/dev/'
      timeout: timeout seconds that passed to pyserial
      cancel_echo: AT command to suppress the echo
      disable_operation: Put modem into a non-operation mode so it will
        not throw unexpected messages.
    """
    self.ser = serial.Serial('/dev/%s' % port, timeout=timeout)

    if cancel_echo:
      self.SendLine('ATE0')

    if disable_operation:
      self.SendLine('AT+CFUN=0')

    # Send few AT commands to
    # 1) make sure the modem is still responsing.
    # 2) Clean previous left messages.
    self.SendLine('AT')
    logging.info('Clean current buffer data %r', self.ser.readlines())

    # Send an AT command and expect 'OK'
    self.SendCommand('AT')
    self.ExpectLine('OK')

  def ReadLine(self):
    '''Reads a line from the modem.'''
    line = self.ser.readline()
    logging.info('modem[ %r', line)
    return line.rstrip('\r\n')

  def SendLine(self, line):
    '''Sends a line to the modem.'''
    logging.info('modem] %r', line)
    self.ser.write(line + '\r')

  def SendCommand(self, command):
    '''Sends a line to the modem and discards the echo.'''
    self.SendLine(command)
    self.ReadLine()

  def ExpectLine(self, expected_line):
    '''Expects a line from the modem.'''
    line = self.ReadLine()
    if line != expected_line:
      raise Error('Expected %r but got %r' % (expected_line, line))
