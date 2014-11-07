# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Provides interfaces to interact with Whale BFT fixture."""

from __future__ import print_function
import logging

import factory_common  # pylint: disable=W0611
import cros.factory.test.fixture.bft_fixture as bft
from cros.factory.test.fixture.whale import color_sensor
from cros.factory.test.fixture.whale import keyboard_emulator
from cros.factory.test.fixture.whale import lcm2004
from cros.factory.test.fixture.whale import servo_client


class WhaleBFTFixture(bft.BFTFixture):
  """Provides interfaces to interact with Whale BFT fixture."""

  # Shortcuts
  # pylint: disable=E1101
  _WHALE_CONTROL = servo_client.WHALE_CONTROL
  _FIXTURE_FEEDBACK = servo_client.FIXTURE_FEEDBACK
  _FEEDBACKS = servo_client.WHALE_FEEDBACKS

  # Mapping of Whale controlled device to Servo control.
  _WHALE_DEVICE = {
      bft.BFTFixture.Device.AC_ADAPTER  : _WHALE_CONTROL.DC,
      bft.BFTFixture.Device.AUDIO_JACK  : _WHALE_CONTROL.AUDIO_PLUG,
      bft.BFTFixture.Device.BATTERY     : _WHALE_CONTROL.BATTERY,
      bft.BFTFixture.Device.LID_MAGNET  : _WHALE_CONTROL.ELECTRO_MAGNET}

  # Mapping from status color to (pass, fail) led status.
  _STATUS_COLOR = {
      bft.BFTFixture.StatusColor.GREEN: ('on', 'off'),
      bft.BFTFixture.StatusColor.RED: ('off', 'on'),
      bft.BFTFixture.StatusColor.OFF: ('off', 'off')}

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
      if color_sensor.ColorSensor.HasRequiredParams(params):
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
    action = 'get device status ' + device
    logging.debug(action)
    whale_device = self._WHALE_DEVICE.get(device)
    if not whale_device:
      raise bft.BFTFixtureException('Unsupported device: ' + device)
    try:
      return (self.Status.ON if self._servo.IsOn(whale_device)
              else self.Status.OFF)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('%s failed. Reason: %s' % (action, e))

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
    logging.debug(action)

    whale_device = self._WHALE_DEVICE.get(device)
    if not whale_device:
      raise bft.BFTFixtureException('Unsupported device: ' + whale_device)
    try:
      self._servo.Set(whale_device, 'on' if engage else 'off')
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to %s. Reason: %s' % (action, e))

  def Ping(self):
    # Try sending an XMLRPC command.
    try:
      self._servo.Get(self._WHALE_CONTROL.PASS_LED)
      logging.debug('ping success')
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
    if not self._color_sensor1:
      raise bft.BFTFixtureException(
          'Failed to check LED color: sensor is not initialized.')
    try:
      return self._color_sensor1.ReadColor() == color
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to check LED color. Reason %s' % e)

  def SetStatusColor(self, color):
    (is_pass, is_fail) = self._STATUS_COLOR.get(color, (None, None))
    if is_pass is None:
      raise bft.BFTFixtureException('Unsupported status color %s' % color)

    try:
      self._servo.MultipleSet([(self._WHALE_CONTROL.PASS_LED, is_pass),
                               (self._WHALE_CONTROL.FAIL_LED, is_fail)])
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to set status color %s. Reason %s' % (color, e))

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

  def IsDUTInFixture(self):
    try:
      return self._servo.IsOn(self._FIXTURE_FEEDBACK.DUT_SENSOR)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to check if DUT in the fixture. Reason: ' + e)

  def CoverStatus(self):
    status = self._servo.MultipleIsOn(self._FEEDBACKS)
    is_open = all([
        status[self._FIXTURE_FEEDBACK.LATERAL_CYLINDER_LEFT_RELEASE],
        status[self._FIXTURE_FEEDBACK.LATERAL_CYLINDER_RIGHT_RELEASE],
        status[self._FIXTURE_FEEDBACK.NEEDLE_CYLINDER_LEFT_RELEASE],
        status[self._FIXTURE_FEEDBACK.NEEDLE_CYLINDER_RIGHT_RELEASE],
        not status[self._FIXTURE_FEEDBACK.HOOK_CYLINDER_LEFT_ACTIVE],
        not status[self._FIXTURE_FEEDBACK.HOOK_CYLINDER_RIGHT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.COVER_CYLINDER_RELEASE],
        not status[self._FIXTURE_FEEDBACK.COVER_CYLINDER_ACTIVE]])

    is_closed = all([
        status[self._FIXTURE_FEEDBACK.LATERAL_CYLINDER_LEFT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.LATERAL_CYLINDER_RIGHT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.NEEDLE_CYLINDER_LEFT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.NEEDLE_CYLINDER_RIGHT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.HOOK_CYLINDER_LEFT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.HOOK_CYLINDER_RIGHT_ACTIVE],
        status[self._FIXTURE_FEEDBACK.COVER_CYLINDER_ACTIVE],
        not status[self._FIXTURE_FEEDBACK.COVER_CYLINDER_RELEASE]])

    if is_open:
      return self.Status.OPEN
    elif is_closed:
      return self.Status.CLOSED
    return self.Status.CLOSING
