# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""SCPI-over-TCP controller."""

import logging
import math
import re
import socket
import struct
import time

from cros.factory.utils import sync_utils


class Error(Exception):
  """A SCPI error.

  Properties:
    error_id: The numeric SCPI error code, if any.
    error_msg: The SCPI error message, if any.
  """

  def __init__(self, msg, error_id=None, error_msg=None):
    super(Error, self).__init__(msg)
    self.error_id = error_id
    self.error_msg = error_msg


MAX_LOG_LENGTH = 800


def _TruncateForLogging(msg):
  if len(msg) > MAX_LOG_LENGTH:
    msg = msg[0:MAX_LOG_LENGTH] + '<truncated>'
  return msg


class LANSCPI:
  """A SCPI-over-TCP controller."""

  def __init__(self, host, port=5025, timeout=3, retries=5, delay=1,
               in_main_thread=False):
    """Connects to a device using SCPI-over-TCP.

    Parameters:
      host: Host to connect to.
      port: Port to connect to.
      timeout: Timeout in seconds.
      retries: maximum attemptis to connect to the host.
      delay: Delay in seconds before issuing the first command.
      in_main_thread: boolean to indicate whether the instance is executed in
                      the main thread. If so, then we use signal to for Timeout.
    """
    self.timeout = timeout
    self.delay = delay
    self.logger = logging.getLogger('SCPI')
    self.host = host
    self.port = port
    self.rfile = None
    self.wfile = None
    self.socket = None
    self.id = None
    self.timeout_use_signal = in_main_thread

    for times in range(1, retries + 1):
      try:
        self.logger.info('Connecting to %s:%d [try %d/%d]...', host, port,
                         times, retries)
        self._Connect()
        return
      except Exception as e:
        self.Close()
        time.sleep(1)
        self.logger.info('Unable to connect to %s:%d: %s', host, port, e)

    raise Error('Failed to connect %s:%d after %d tries' % (
        host, port, retries))

  def _Connect(self):
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    with sync_utils.Timeout(self.timeout, self.timeout_use_signal):
      self.logger.debug('] Connecting to %s:%d...', self.host, self.port)
      self.socket.connect((self.host, self.port))

    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    self.rfile = self.socket.makefile('rb', -1)  # Default buffering
    self.wfile = self.socket.makefile('wb', 0)   # No buffering

    self.logger.info('Connected')

    # Give equipment time to warm up if required so.
    time.sleep(self.delay)
    self.id = self.Query(b'*IDN?')

  def Close(self):
    self.logger.info('Destroying')
    if self.rfile:
      self.rfile.close()
    if self.wfile:
      self.wfile.close()
    if self.socket:
      self.socket.close()

  def Reopen(self):
    """Closes and reopens the connection."""
    self.Close()
    time.sleep(1)
    self._Connect()

  def Send(self, commands, wait=True):
    """Sends a command or series of commands.

    Args:
      commands: The commands to send.  May be list, or a string if
          just a single command.
      wait: If True, issues an *OPC? command after the final
          command to block until all commands have completed.
    """
    if isinstance(commands, bytes):
      self.Send([commands], wait)
      return

    self._WriteLine(b'*CLS')
    for command in commands:
      if command[-1] == '?':
        raise Error('Called Send with query %r' % command)
      self._WriteLine(command)
      self._WriteLine(b'SYST:ERR?')

    errors = []
    error_id = None
    error_msg = None
    for command in commands:
      ret = self._ReadLine()
      if ret != b'+0,"No error"':
        errors.append('Issuing command %r: %r' % (command, ret))
      if not error_id:
        # We don't have an error ID for the exception yet;
        # try to parse the SCPI error.
        match = re.match(br'^([-+]?\d+),"(.+)"$', ret)
        if match:
          error_id = int(match.group(1))
          error_msg = match.group(2)

    if errors:
      raise Error('; '.join(errors), error_id, error_msg)

    if wait:
      self._WriteLine(b'*OPC?')
      ret = self._ReadLine()
      if int(ret) != 1:
        raise Error('Expected 1 after *OPC? but got %r' % ret)

  def Query(self, command, formatter=None):
    """Issues a query, returning the result.

    Args:
      command: The command to issue.
      formatter: If present, a function that will be applied to the query
          response to parse it.  The formatter may be int(), float(), a
          function from the "Formatters" section at the bottom of this
          file, or any other function that accepts a single string
          argument.
    """
    if b'?' not in command:
      raise Error('Called Query with non-query %r' % command)
    self._WriteLine(b'*CLS')
    self._WriteLine(command)

    self._WriteLine(b'*ESR?')
    self._WriteLine(b'SYST:ERR?')

    line1 = self._ReadLine()
    line2 = self._ReadLine()
    # On success, line1 is the queried value and line2 is the status
    # register.  On failure, line1 is the status register and line2
    # is the error string.  We do this to make sure that we can
    # detect an unknown header rather than just waiting forever.
    if b',' in line2:
      raise Error('Error issuing command %r: %r' % (command, line2))

    # Success!  Get SYST:ERR, which should be +0
    line3 = self._ReadLine()
    if line3 != b'+0,"No error"':
      raise Error('Error issuing command %r: %r' % (command, line3))

    if formatter:
      line1 = formatter(line1)
    return line1

  def QueryWithoutErrorChecking(self, command,
                                expected_length, formatter=None):
    """Issues a query, returning the fixed-length result without error checking.

    This is a specialized version of Query(). Error checking is disabled and
    result is assumed to be fixed length to increase the speed.

    Args:
      command: The command to issue.
      expected_length: expected length of result.
      formatter: If present, a function that will be applied to the query
          response to parse it.  The formatter may be int(), float(), a
          function from the "Formatters" section at the bottom of this
          file, or any other function that accepts a single string
          argument.
    """
    if b'?' not in command:
      raise Error('Called Query with non-query %r' % command)
    self._WriteLine(command)
    line1 = self._ReadBinary(expected_length)
    if formatter:
      line1 = formatter(line1)
    return line1

  def Quote(self, string):
    """Quotes a string."""
    # TODO(jsalz): Use the real IEEE 488.2 string format.
    return '"%s"' % string

  def _ReadLine(self):
    """Reads a single line, timing out in self.timeout seconds."""

    with sync_utils.Timeout(self.timeout, self.timeout_use_signal):
      if not self.timeout:
        self.logger.debug('[ (waiting)')
      ch = self.rfile.read(1)

      if ch == b'#':
        # Binary format, which is:
        #
        # 1. A pound sign
        # 2. A base-10 representation of the number of characters in the
        #    base-10 representation of the payload length
        # 3. The payload length, in base-10
        # 4. The payload
        # 5. A newline character
        #
        # E.g., "#17FOO BAR\n" (where 7 is the length of "FOO BAR" and
        # 1 is the length of "7").
        #
        # Note that if any of this goes haywire, the connection will be
        # basically unusable since there is no way to know where we
        # are in the binary data.
        length_length = int(self.rfile.read(1))
        length = int(self.rfile.read(length_length))
        ret = self.rfile.read(length)
        ch = self.rfile.read(1)
        if ch != b'\n':
          raise Error('Expected newline at end of binary data')

        if self.logger.isEnabledFor(logging.DEBUG):
          self.logger.debug('[binary %r', _TruncateForLogging(ret))
        return ret
      if ch == b'\n':
        # Empty line
        self.logger.debug('[empty')
        return b''
      ret = ch + self.rfile.readline().rstrip(b'\n')
      if self.logger.isEnabledFor(logging.DEBUG):
        self.logger.debug('[ %s', _TruncateForLogging(ret))
      return ret

  def _ReadBinary(self, expected_length):
    """Reads a binary of fixed bytes."""
    with sync_utils.Timeout(self.timeout, self.timeout_use_signal):
      if not self.timeout:
        self.logger.debug('[ (waiting)')
      ret = self.rfile.read(expected_length)
      ch = self.rfile.read(1)
      if ch != b'\n':
        raise Error('Expected newline at end of binary data')
      return ret

  def _WriteLine(self, command):
    """Writes a single line."""
    if b'\n' in command:
      raise Error('Newline in command: %r' % command)
    self.logger.debug('] %s', command)
    self.wfile.write(command + b'\n')


#
# Formatters.
#

FLOATS = lambda s: [float(f) for f in s.split(',')]


def BINARY_FLOATS(binary_string):
  if len(binary_string) % 4:
    raise Error('Binary float data contains %d bytes '
                '(not a multiple of 4)' % len(binary_string))
  return struct.unpack('>' + 'f' * (len(binary_string) // 4), binary_string)


def BINARY_FLOATS_WITH_LENGTH(expected_length):
  def formatter(binary_string):
    ret = BINARY_FLOATS(binary_string)
    if len(ret) == 1 and math.isnan(ret[0]):
      raise Error('Unable to retrieve array')
    if len(ret) != expected_length:
      raise Error('Expected %d elements but got %d' % (
          expected_length, len(ret)))
    return ret

  return formatter
