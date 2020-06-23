# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper for talking with a tty modem."""

import logging
import re

import serial

from cros.factory.utils import type_utils

_COMMAND_RETRY_TIMES = 5
_RECEIVE_RETRY_TIMES = 10


class Modem:

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
      self.SendCommandWithCheck('ATE0')

    if disable_operation:
      self.SendCommandWithCheck('AT+CFUN=0')

    # Send an AT command and expect 'OK'
    self.SendCommandWithCheck('AT')

  def ReadLine(self):
    """Reads a line from the modem."""
    line = self.ser.readline()
    logging.info('modem[ %r', line)
    return line.rstrip('\r\n')

  def SendLine(self, line):
    """Sends a line to the modem."""
    logging.info('modem] %r', line)
    self.ser.write(line + '\r')

  def SendCommand(self, command):
    """Sends a line to the modem and discards the echo."""
    self.SendLine(command)
    self.ReadLine()

  def SendCommandWithCheck(self, command, retry_times=_COMMAND_RETRY_TIMES):
    """Sends a command to the modem.

    SendCommand function allow retry when response is not OK.

    Returns:
      response: A list contains all success responses from modem.
    """
    retries = 0
    while retries < retry_times:
      self.SendLine(command)
      response = self.GetResponse()
      if response[-1] == 'OK':
        break
      retries += 1
    return response

  def GetResponse(self, retry_times=_RECEIVE_RETRY_TIMES):
    """Gets response from modem.

    A formal response should be OK or ERROR at the end of response.

    Returns:
      response: A list contains all response from modem.

    Raises:
      Error when getting response exceeds time limit
      (serial timeout * retry_times).
    """
    response = []
    retries = 0
    while retries < retry_times:
      line = self.ReadLine()
      if line:
        response.append(line)
        # TODO (henryhsu): The response may have "+CME ERROR: <errno>".
        # If we will use ME command in the future, we will need handle this
        # error type.
        if line in ['OK', 'ERROR']:
          return response
      else:
        retries += 1
    raise type_utils.Error('Cannot get entire response: %r' % (response))

  def ExpectResponse(self, expected_msg, modem_response):
    """Checks expected messages from modem.

    Args:
      expected_msg: expected messages can be list or string.
      modem_response: A list contains all responses from modem.

    Raises:
      Error when results mismatch.
    """
    if isinstance(expected_msg, str):
      expected_msg = [expected_msg]
    for msg in expected_msg:
      if msg not in modem_response:
        raise type_utils.Error(
            'Expected %r but got %r' % (expected_msg, modem_response))

  def ExpectLine(self, expected_line):
    """Expects a line from the modem."""
    line = self.ReadLine()
    if line != expected_line:
      raise type_utils.Error('Expected %r but got %r' % (expected_line, line))

  def ExpectMultipleLines(self, expected_regex):
    """Expects a multiple line regular expression."""
    lines = self.ser.readlines()
    for line in lines:
      logging.info('modem[ %r', line)
    if not re.search(expected_regex, ''.join(lines), re.MULTILINE | re.DOTALL):
      raise type_utils.Error('Expected %r but got %r' % (expected_regex, lines))
