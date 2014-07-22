# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Provides interfaces to interact with Whale BFT fixture."""

import logging

import factory_common  # pylint: disable=W0611
import cros.factory.test.fixture.bft_fixture as bft
from cros.factory.test.fixture.whale import color_sensor
from cros.factory.test.fixture.whale import keyboard_emulator
from cros.factory.test.fixture.whale import lcm2004
from cros.factory.test.fixture.whale import servo_client


class WhaleBFTFixture(bft.BFTFixture):
  """Provides interfaces to interact with Whale BFT fixture."""

  # shortcut
  BFT = bft.BFTFixture

  # Mappings from Device name to Servo command/attribute.
  _SERVO_COMMAND = {
      BFT.Device.AC_ADAPTER  : 'whale_dc_in',
      BFT.Device.AUDIO_JACK  : 'whale_audio_plug_det',
      BFT.Device.EXT_DISPLAY : None,
      BFT.Device.LID_MAGNET  : 'whale_elctro_magnet',
      BFT.Device.USB_0       : None,
      BFT.Device.USB_1       : None,
      BFT.Device.USB_2       : None}

  # Mapping from status color to (pass, fail) led status.
  _STATUS_COLOR = {
      BFT.StatusColor.GREEN: ('on', 'off'),
      BFT.StatusColor.RED: ('off', 'on'),
      BFT.StatusColor.OFF: ('off', 'off'),
      }

  # Mapping from servo status to BFTFixture.Status enum.
  _STATUS = {
      'on': BFT.Status.ON,
      'off': BFT.Status.OFF}

  def __init__(self):
    super(WhaleBFTFixture, self).__init__()
    self._servo = None
    self._color_sensor1 = None
    self._keyboard_emulator = None
    self._lcm = None

  def Init(self, **params):
    """Sets up an XML-RPC proxy to BFTFixture's BeagleBone Servo.

    Args:
      **params: Parameters of ServoClient and ColorSensor.
    """
    try:
      self._servo = servo_client.ServoClient(
          host=params['host'], port=params['port'])
      self._color_sensor1 = color_sensor.ColorSensor(
          servo=self._servo, sensor_index=1, params=params)
      self._keyboard_emulator = keyboard_emulator.KeyboardEmulator(self._servo)
      self._lcm = lcm2004.Lcm2004(self._servo)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to Init(). Reason: %s' % e)

  def Disconnect(self):
    # No need to disconnect it.
    pass

  def GetDeviceStatus(self, device):
    action = 'get device status %s' % device
    logging.info(action)
    command = self._SERVO_COMMAND.get(device)
    if not command:
      raise bft.BFTFixtureException('Unsupported action: ' + action)
    try:
      servo_device_status = getattr(self._servo, command)
      status = self._STATUS.get(servo_device_status)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to %s. Reason: %s' % (action, e))

    if status is None:
      raise bft.BFTFixtureException(
          'Failed to %s. Reason: unrecognized device status from servo: %s' % (
              action, servo_device_status))
    return status

  def SetDeviceEngaged(self, device, engage):
    """Engages/disengages a device.

    Issues a command to BFT fixture to engage/disenage a device.
    The device can be either a peripheral device of the board or a
    device of the fixture.

    Args:
      device: device defined in BFTFixture.Device
      engage: True to engage; False to disengage.
    """
    action = '%s device %s' % ('engage' if engage else 'disengage', device)
    logging.info(action)

    command = self._SERVO_COMMAND.get(device)
    if not command:
      raise bft.BFTFixtureException('Unsupported action: ' + action)
    try:
      setattr(self._servo, command, 'on' if engage else 'off')
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to %s. Reason: %s' % (action, e))

  def Ping(self):
    # Try sending an XMLRPC command.
    try:
      _ = self._servo.whale_pass_led
      logging.info('ping success')
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to connect to servo. Reason: %s' % e)

  def CheckPowerRail(self):
    raise NotImplementedError

  def CheckExtDisplay(self):
    raise NotImplementedError

  def GetFixtureId(self):
    raise NotImplementedError

  def ScanBarcode(self):
    raise NotImplementedError

  def IsLEDColor(self, color):
    try:
      return self._color_sensor1.ReadColor() == color
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to check LED color. Reason %s' % e)

  def SetStatusColor(self, color):
    (pass_led, fail_led) = self._STATUS_COLOR.get(color, (None, None))
    if pass_led is None:
      raise bft.BFTFixtureException('Unsupported status color %s' % color)

    try:
      self._servo.whale_pass_led = pass_led
      self._servo.whale_fail_led = fail_led
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to set status color. Reason %s' % e)

  def SimulateKeystrokes(self):
    self._keyboard_emulator.SimulateKeystrokes()

  def SimulateKeyPress(self, bitmask, duration_secs):
    try:
      self._keyboard_emulator.KeyPress(int(bitmask, 0), float(duration_secs))
    except ValueError as e:
      raise bft.BFTFixtureException('Failed to convert bitmask. Reason %s' % e)

  def SetLcmText(self, row, message):
    try:
      self._lcm.SetLcmText(row, message)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to show a message to LCM. Reason %s' % e)

  def IssueLcmCommand(self, action):
    try:
      self._lcm.IssueLcmCommand(action)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to execute an action to LCM. Reason %s' % e)
