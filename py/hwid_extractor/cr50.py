# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import codecs
import enum
import logging
import re
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
# The maximum number of retries of the failed `rma_auth` commands and the
# interval between retries.
CR50_RMA_AUTH_MAX_RETRY = 3
CR50_RMA_AUTH_RETRY_INTERVAL = 1
# Timeout of testlab enable / disable physical presence check.
CR50_TESTLAB_PP_TIMEOUT = 10


class TestlabState(enum.Enum):
  ENABLED = 'enabled'
  DISABLED = 'disabled'


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

  def ChangeTestlabState(self, state):
    """Set testlab state to `state`.

    Changing the testlab state requires physical presence check (PP).

    Args:
      state: The TestlabState to be changed to.
    Returns:
      True if the state changed successfully. False if PP timeout.
    Raises:
      RuntimeError if PP tokens cannot be found in the outputs.
    """
    with serial.Serial(self._cr50_uart_pty,
                       timeout=SERIAL_CONSOLE_TIMEOUT) as ser:
      logging.debug('Serial init.')
      self._Cr50CommandInner(ser, f'ccd testlab {state.value}')
      end_time = time.time() + CR50_TESTLAB_PP_TIMEOUT
      line = ''
      while time.time() < end_time:
        line += ser.read_until(b'\n', CR50_CONSOLE_BUFFER_SIZE_BYTES).decode()
        if not line.endswith('\n'):
          continue

        logging.debug(line)
        if 'Press the physical button now!' in line:
          end_time = time.time() + CR50_TESTLAB_PP_TIMEOUT
        elif 'Physical presence check timeout' in line:
          return False
        elif f'CCD test lab mode {state.value}' in line:
          return True
        line = ''

    raise RuntimeError(
        'Cannot get Physical presence check status. Testlab may not be '
        'supported. Or permission was denied.')


class Cr50:
  """A high level interface of Cr50.

  Args:
    cr50_uart_pty: The device of cr50 console.
  """

  def __init__(self, cr50_uart_pty):
    self._cr50_console = Cr50Console(cr50_uart_pty)

  def GetRLZ(self):
    """Get RLZ code from Cr50.

    Examples of the output of bid command:
      Board ID: 57565257:a8a9ada8, flags 00007f7f
      Board ID: 59565251, flags 00000010

    Returns:
      RLZ code or None
    """
    output = self._cr50_console.Command('bid')
    m = re.search(r'Board ID: ([0-9A-Fa-f]+?)[:,]', output)
    if not m:
      return None
    hex_rlz = m.group(1)
    try:
      return codecs.decode(hex_rlz, 'hex').decode()
    except UnicodeDecodeError:
      return None

  def GetChallenge(self):
    """Get the rma_auth challenge

    There are two challenge formats
    "
    ABEQ8 UGA4F AVEQP SHCKV
    DGGPR N8JHG V8PNC LCHR2
    T27VF PRGBS N3ZXF RCCT2
    UBMKP ACM7E WUZUA A4GTN
    "
    and
    "
    generated challenge:
    CBYRYBEMH2Y75TC...rest of challenge
    "
    support extracting the challenge from both.

    `rma_auth` may fail if the interval between the last call is too short.
    Retry if the command return `RMA Auth error`. After these retries the
    command is considered to be failed.

    Returns:
      The RMA challenge with all whitespace removed.
    """
    for unused_i in range(CR50_RMA_AUTH_MAX_RETRY):
      output = self._cr50_console.Command('rma_auth').strip()
      if 'RMA Auth error' not in output:
        break
      time.sleep(CR50_RMA_AUTH_RETRY_INTERVAL)
    if 'generated challenge:' in output:
      return output.split('generated challenge:')[-1].strip()
    challenge = ''.join(re.findall(r' \S{5}' * 4, output))
    # Remove all whitespace
    return ''.join(challenge.split())

  def GetTestlabState(self):
    """Get the state of testlab.

    Example output:
      CCD test lab mode enabled
      CCD test lab mode disabled

    Returns:
      TestlabState, or None if the state can not be determined.
    """
    output = self._cr50_console.Command('ccd testlab')
    state = output.split('mode')[-1].strip().lower()
    logging.info('Testlab: %s', state)
    try:
      return TestlabState(state)
    except ValueError:
      return None

  def ForceOpen(self):
    """Force CCD to be opened.

    To simplify the process, if the testlab is enabled, call this function to
    force ccd to be non-restricted. This only works when testlab is enabled.

    Returns:
      True if ccd is opened.
    """
    self._cr50_console.Command('ccd testlab open')
    self._cr50_console.Command('ccd reset factory')
    # Wait for Cr50 resetting.
    time.sleep(1)
    return self.IsRestricted()

  def IsRestricted(self):
    """The restricted status of the device.

    Check the output of `ccd` command. If it contains 'IfOpened' or
    'IfUnlocked', the device is considered as restricted.

    If 'Capabilities' is not in the output of `ccd` command, the execution of
    `ccd` command is considered as failed.

    Returns:
      True if the device is restricted.
    Raises:
      ValueError: Cannot get the output of `ccd` from device.
    """
    logging.info('Update restricted status')
    output = self._cr50_console.Command('ccd')
    if 'Capabilities' not in output:
      logging.error('`Capabilities` not in output of `ccd`, output:\n%s',
                    output)
      raise ValueError('Could not get ccd output.')

    is_restricted = 'IfOpened' in output or 'IfUnlocked' in output
    logging.info('Restricted status: %s', is_restricted)
    return is_restricted

  def Unlock(self, authcode):
    """Unlock the device with `authcode`.

    If unlock successfully, Cr50 will reboot and may be unresponsive for several
    seconds.

    Args:
      authcode: The authcode for rma_auth to unlock the device.
    Returns:
      True if unlock successfully.
    """
    logging.info('Unlock the device with authcode: %s', authcode)
    output = self._cr50_console.Command(f'rma_auth {authcode}')
    logging.info('Unlock result:\n%s', output)
    return 'process_response: success!' in output

  def Lock(self):
    """Lock the device.

    Assume that the device is not restricted.

    Returns:
      True if lock successfully.
    """
    logging.info('Lock the device')
    # `ccd reset` needs ccd to be in open state.
    self._cr50_console.Command('ccd open')
    self._cr50_console.Command('ccd reset')
    # Wait for Cr50 resetting.
    time.sleep(1)
    self._cr50_console.Command('ccd lock')
    # Wait for Cr50 resetting.
    time.sleep(1)
    return self.IsRestricted()

  def _SetTestlabState(self, state):
    current_state = self.GetTestlabState()
    if current_state is None:
      raise RuntimeError('Testlab may not be supported on this devices.')
    if current_state == state:
      return True
    # Testlab needs ccd to be in open state.
    self._cr50_console.Command('ccd open')
    return self._cr50_console.ChangeTestlabState(state)

  def EnableTestlab(self):
    """Enable testlab.

    Assume that the device is not restricted.

    Returns:
      True if testlab is enabled.
    """
    return self._SetTestlabState(TestlabState.ENABLED)

  def DisableTestlab(self):
    """Disable testlab.

    Assume that the device is not restricted.

    Returns:
      True if testlab is disabled.
    """
    return self._SetTestlabState(TestlabState.DISABLED)
