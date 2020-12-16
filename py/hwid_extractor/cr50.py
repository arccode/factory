# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time

import serial

# Timeout for the unresponding serial console.
SERIAL_CONSOLE_TIMEOUT = 1
# Buffer size for each read of cr50 uart console.
CR50_CONSOLE_BUFFER_SIZE_BYTES = 4096
# The maximum number of retries of dropping the console output and the interval
# between retries.
CR50_DROP_OUTPUT_MAX_RETRY = 20
CR50_DROP_OUTPUT_INTERVAL = 0.05
# The maximum number of retries of the failed commands and the interval between
# retries.
CR50_COMMAND_MAX_RETRY = 3
CR50_COMMAND_RETRY_INTERVAL = 1


class Cr50Console:
  """An interface of Cr50 console to send commands and receive the outputs.

  Args:
    cr50_uart_pty: The pty device of cr50 uart console.
  """

  def __init__(self, cr50_uart_pty):
    self._cr50_uart_pty = cr50_uart_pty

  @staticmethod
  def _DropUnusedCr50ConsoleOutput(ser):
    """Drop the unused output from cr50 console.

    Sometime console prints debug messages before sending commands. Drop
    those lines.

    Note that if the console has no output in `CR50 DROP OUTPUT INTERVAL`
    seconds, it is considered that all outputs are dropped. However, in some
    cases, some lines may be printed after a few seconds of silence.

    Returns:
      True if all the outputs has been dropped.
    """
    for unused_i in range(CR50_DROP_OUTPUT_MAX_RETRY):
      time.sleep(CR50_DROP_OUTPUT_INTERVAL)
      if ser.in_waiting == 0:
        return True
      ser.reset_input_buffer()
    return False

  @classmethod
  def _Cr50CommandInner(cls, ser, cmd):
    """Execute the command on the cr50 console."""
    if not cls._DropUnusedCr50ConsoleOutput(ser):
      return ''

    end_of_cmd = '__END_OF_COMMAND__'
    start_token = f'{cmd}\r\n'.encode()
    end_token = f'> {end_of_cmd}'.encode()
    # First '\n' forces the console to print a new line (b'>').
    ser.write(f'\n{cmd}\n{end_of_cmd}\n'.encode())

    output = ser.read_until(start_token, CR50_CONSOLE_BUFFER_SIZE_BYTES)
    if not output.endswith(start_token):
      return ''
    output = ser.read_until(end_token, CR50_CONSOLE_BUFFER_SIZE_BYTES)
    if not output.endswith(end_token):
      return ''
    try:
      return output.decode().rpartition('>')[0].strip()
    except UnicodeDecodeError:
      return ''

  def Command(self, cmd, max_retry=CR50_COMMAND_MAX_RETRY,
              retry_interval=CR50_COMMAND_RETRY_INTERVAL):
    """Execute the command on the cr50 console.

    The console may not be ready to communicate with. Retry if the output is
    empty. After these retries the command is considered to be failed.

    Returns:
      The output of the command.
    """
    logging.info('Execute command: "%s" on console: %s', cmd,
                 self._cr50_uart_pty)
    with serial.Serial(self._cr50_uart_pty,
                       timeout=SERIAL_CONSOLE_TIMEOUT) as ser:
      logging.debug('Serial init.')
      for unused_i in range(max_retry):
        output = self._Cr50CommandInner(ser, cmd)
        if output:
          break
        time.sleep(retry_interval)
      if not output:
        logging.info('Output of Command: "%s" on console "%s" is empty.', cmd,
                     self._cr50_uart_pty)
      logging.debug('Cr50 command: "%s":\n%s', cmd, output)
    return output
