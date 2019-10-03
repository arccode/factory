# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import serial

from cros.factory.test.fixture import bft_fixture
from cros.factory.test.utils import serial_utils


def _CommandStr(command):
  """Formats one-byte command with 0xFF format.

  Returns:
    One-byte command in 0x%02X format. For non one-byte-str input,
    returns 'invalid command' instead.
  """
  if isinstance(command, str):
    if len(command) == 1:
      return '0x%02X' % ord(command)
    return 'invalid command %r, len:%d != 1' % (command, len(command))
  return 'invalid command %r: not a string.' % command


class SpringBFTFixture(bft_fixture.BFTFixture):
  """Provides interfaces to interact with BFT fixture for Spring board."""
  # pylint: disable=abstract-method

  # Define Spring BFT fixture's support devices' command.
  # device: (engage_command, disengage_command)
  # None means unsupported.
  Device = bft_fixture.BFTFixture.Device
  DEVICE_COMMAND = {
      Device.AC_ADAPTER: (chr(0xC8), chr(0xD0)),
      Device.AUDIO_JACK: (chr(0xCC), chr(0xCD)),
      Device.EXT_DISPLAY: (chr(0xCB), chr(0xD0)),
      Device.LID_MAGNET: (chr(0xC2), chr(0xC3)),
      Device.USB_0: (chr(0xCA), chr(0xD0)),
      Device.USB_1: (None, None),
      Device.USB_2: (None, None)}

  # (command, response) pairs for fixture to check LED colors.
  LEDColor = bft_fixture.BFTFixture.LEDColor
  LED_CHECK_COMMAND = {
      LEDColor.RED: (chr(0xC4), chr(0xB4)),
      LEDColor.GREEN: (chr(0xC5), chr(0xB5)),
      LEDColor.YELLOW: (chr(0xC6), chr(0xB6)),
      LEDColor.OFF: (chr(0xD4), chr(0xFC))}

  StatusColor = bft_fixture.BFTFixture.StatusColor
  STATUS_COLOR_COMMAND = {
      StatusColor.GREEN: chr(0xCE),
      StatusColor.RED: chr(0xCF),
  }

  DEFAULT_RESPONSE = chr(0xFA)
  ENGAGE_BARCODE_SCANNER = chr(0xC7)
  ENGAGE_KEYBOARD_SCANNER = chr(0xC1)

  SYSTEM_STATUS_COMMAND = {
      bft_fixture.BFTFixture.SystemStatus.BACKLIGHT: {
          'code': chr(0xD6),
          'fail_message': 'Failed to check backlight',
          'status_map': {
              chr(0xFA): bft_fixture.BFTFixture.Status.ON,
              chr(0xFE): bft_fixture.BFTFixture.Status.OFF,
          }}}

  # Defaut value of self._serial.
  _serial = None

  # Fixture ID. Obtained from Init().
  fixture_id = 0

  # pylint: disable=arguments-differ
  def GetSystemStatus(self, probe):
    """Reads internal status of a testing board.

    Args:
      probe: the probe to read.

    Returns:
      BFTFixture.Status

    Raises:
      BFTFixtureException: when the specified probe not supported, or the
                           returned result was not in status map.
    """
    if probe not in self.SYSTEM_STATUS_COMMAND:
      raise bft_fixture.BFTFixtureException(
          'Fixture does not support %s' % probe)

    cmd = self.SYSTEM_STATUS_COMMAND[probe]
    self._Send(cmd['code'], cmd['fail_message'])
    fixture_status = self._Recv(cmd['fail_message'])
    if fixture_status in cmd['status_map']:
      return cmd['status_map'][fixture_status]
    raise bft_fixture.BFTFixtureException(cmd['fail_message'])

  def Init(self, **serial_params):
    """Sets up RS-232 connection.

    Args:
      **serial_params: Parameters of pySerial's Serial().
          'port' should be specified. If port cannot be predetermined,
          you can specify 'driver' and it'll use FindTtyByDriver() to
          locate the first /dev/ttyUSB* which uses the driver.
    """
    if 'driver' in serial_params:
      serial_params['port'] = serial_utils.FindTtyByDriver(
          serial_params['driver'])
      if not serial_params['port']:
        raise bft_fixture.BFTFixtureException('Cannot find TTY with driver %s' %
                                              serial_params['driver'])
      # After lookup, remove 'driver' from serial_params as OpenSerial
      # doesn't accept 'driver' param.
      del serial_params['driver']
    try:
      self._serial = serial_utils.OpenSerial(**serial_params)
    except serial.SerialException as e:
      raise bft_fixture.BFTFixtureException(
          'Cannot connect to BFT fixture: %s' % e)

    # Get fixture each time we establish a BFT connection as operator may
    # use different fixture to retest a board and we want to know which
    # fixture actually used.
    self._ObtainFixtureId()

  def Disconnect(self):
    if self._serial:
      self._serial.close()

  def _Send(self, command, fail_message):
    """Sends a one-char command to BFT fixture.

    Args:
      command: a one-char string.
      fail_message: error message to prepend to BFTFixtureException.
    """
    if not self._serial:
      raise bft_fixture.BFTFixtureException(
          'BFT connection is not established yet.')

    try:
      write_len = self._serial.write(command)
    except serial.SerialTimeoutException as e:
      raise bft_fixture.BFTFixtureException(
          '%sSend command %s to fixture %d timeout: %s' %
          (fail_message, self.fixture_id, _CommandStr(command), e))

    if write_len != 1:
      raise bft_fixture.BFTFixtureException(
          '%sSend command %s to fixture %d failed.' %
          (fail_message, self.fixture_id, _CommandStr(command)))

  def _Recv(self, fail_message):
    """Receives a response from BFT fixture.

    Args:
      fail_message: error message to prepend to BFTFixtureException.
    Returns:
      The response string.
    """
    try:
      return self._serial.read()
    except serial.SerialTimeoutException as e:
      raise bft_fixture.BFTFixtureException(
          '%sReceive timeout: %s' % (fail_message, e))

  def _SendRecv(self, command, expect, fail_message):
    """Sends a command and expects a response.

    Args:
      command: a one-char string to send to BFT fixture.
      expect: a one-char string for expecting the reply. Default 0xFA.
      fail_message: error message to prepend to BFTFixtureException.
    """
    self._Send(command, fail_message)

    actual = self._Recv(fail_message)
    if actual != expect:
      raise bft_fixture.BFTFixtureException(
          '%s Sent:%s. Expect response:%s, actual:%s.' %
          (fail_message, _CommandStr(command), _CommandStr(expect),
           _CommandStr(actual)))

    logging.info(
        'Successfully sent %s to fixture %d. Got expected response %s.',
        _CommandStr(command), self.fixture_id, _CommandStr(expect))

  def _SendRecvDefault(self, command, fail_message):
    """Like _SendRecv, but expecting 0xFA response."""
    self._SendRecv(command, self.DEFAULT_RESPONSE, fail_message)

  def SetDeviceEngaged(self, device, engage):
    """Engages/disengages a device.

    Issues a command to BFT fixture to engage/disenage a device.
    The device can be either a peripheral device of the board or a
    device of the fixture.

    Args:
      device: device defined in BFTFixture.Device
      engage: True to engage; False to disengage.
    """
    action_str = '%s device %s' % ('engage' if engage else 'disengage',
                                   device)
    logging.info(action_str)

    command = None
    if device in self.DEVICE_COMMAND:
      command = self.DEVICE_COMMAND[device][0 if engage else 1]
    if not command:
      raise bft_fixture.BFTFixtureException('Unsupported action: ' + action_str)

    self._SendRecvDefault(command, 'Failed to %s. ' % action_str)

  def Ping(self):
    self._SendRecv(chr(0xE0), chr(0xE1), 'Failed to ping the fixture. ')

  def CheckPowerRail(self):
    self._SendRecv(chr(0xD2), chr(0xE2),
                   'Failed to check DUT\'s power rail voltage. ')

  def CheckExtDisplay(self):
    self._SendRecv(chr(0xD5), chr(0xFD),
                   'Failed to detect color on external display.')

  def _ObtainFixtureId(self):
    """Obtains fixture ID.

    It should only be called in Init(). We shall get fixture ID for each
    fixture connection as we are not sure if an operator retest the board
    with another fixture.
    """
    FAIL_MESSAGE = 'Failed to get fixture ID. '
    self._Send(chr(0xD3), FAIL_MESSAGE)
    recv = self._Recv(FAIL_MESSAGE)
    self.fixture_id = ord(recv[0])
    logging.info('Got fixture ID: %d', self.fixture_id)

  def GetFixtureId(self):
    return self.fixture_id

  def ScanBarcode(self):
    self._SendRecvDefault(self.ENGAGE_BARCODE_SCANNER,
                          'Failed to scan barcode. ')

  def SimulateKeystrokes(self):
    self._SendRecvDefault(self.ENGAGE_KEYBOARD_SCANNER,
                          'Failed to simulate keystrokes. ')

  def IsLEDColor(self, color):
    if color not in self.LED_CHECK_COMMAND:
      raise bft_fixture.BFTFixtureException('Invalid LED color %r' % color)

    (command, expect) = self.LED_CHECK_COMMAND[color]
    self._Send(command, 'Fail to check %s LED. ' % color)
    response = self._Recv('Fail to check %s LED. ' % color)
    if response == expect:
      logging.info(
          'Successfully sent %s to fixture %d. Got matched response %s',
          _CommandStr(command), self.fixture_id, _CommandStr(response))
    else:
      logging.warning(
          'Successfully sent %s to fixture %d. Response mismatch: '
          'expected:%s  actual:%s',
          _CommandStr(command), self.fixture_id, _CommandStr(expect),
          _CommandStr(response))
    return response == expect

  def SetStatusColor(self, color):
    if color not in self.STATUS_COLOR_COMMAND:
      raise bft_fixture.BFTFixtureException('Invalid status color %r' % color)
    self._SendRecvDefault(self.STATUS_COLOR_COMMAND[color],
                          'Unable to set status color to %s' % color)
