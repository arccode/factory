# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Provides interfaces to interact with Whale BFT fixture."""

import ast
import logging
import os

from cros.factory.test.fixture import bft_fixture as bft
from cros.factory.test.fixture.whale import color_sensor
from cros.factory.test.fixture.whale import keyboard_emulator
from cros.factory.test.fixture.whale import lcm2004
from cros.factory.test.fixture.whale import servo_client
from cros.factory.utils import process_utils
from cros.factory.utils import ssh_utils


class WhaleBFTFixture(bft.BFTFixture):
  """Provides interfaces to interact with Whale BFT fixture."""

  POWER_KEY = '0x2000'

  # Shortcuts
  _WHALE_CONTROL = servo_client.WHALE_CONTROL
  _WHALE_BUTTON = servo_client.WHALE_BUTTON
  _FIXTURE_FEEDBACK = servo_client.FIXTURE_FEEDBACK
  _FEEDBACKS = servo_client.WHALE_FEEDBACKS
  _WHALE_INAS = servo_client.WHALE_INAS
  _WHALE_ADC = servo_client.WHALE_ADC

  # Mapping of Whale controlled device to Servo control.
  _WHALE_DEVICE = {
      bft.BFTFixture.Device.AUDIO_JACK: _WHALE_CONTROL.AUDIO_PLUG,
      bft.BFTFixture.Device.BATTERY: _WHALE_CONTROL.BATTERY,
      bft.BFTFixture.Device.LID_MAGNET: _WHALE_CONTROL.ELECTRO_MAGNET,
      bft.BFTFixture.Device.C0_CC2_DUT: _WHALE_CONTROL.DC,
      bft.BFTFixture.Device.C1_CC2_DUT: _WHALE_CONTROL.OUTPUT_RESERVE_1,
      bft.BFTFixture.Device.LID_HALL_MAGNET: _WHALE_CONTROL.LID_HALL_MAGNET,
      bft.BFTFixture.Device.BASE_HALL_MAGNET: _WHALE_CONTROL.BASE_HALL_MAGNET,
      bft.BFTFixture.Device.BASE_CHARGER: _WHALE_CONTROL.BASE_CHARGER, }

  # Add 8 GPIOs on krill board PCA9534
  _WHALE_DEVICE.update({
      'krill_pca9534_p%d' % i: 'krill_pca9534_p%d' % i for i in range(8)
  })

  # Add whale_fixture_ctrl
  _WHALE_DEVICE.update({
      'whale_fixture_ctrl%d' % i: 'whale_fixture_ctrl%d' % i
      for i in range(1, 7)
  })

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
    self._nuc_host = None
    self._nuc_dut_serial_path = None
    self._testing_rsa_path = None

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
      self._nuc_host = params.get('nuc_host')
      self._nuc_dut_serial_path = params.get('nuc_dut_serial_path')
      self._testing_rsa_path = params.get('testing_rsa_path')
      if self._testing_rsa_path:
        # Make identity file less open to make ssh happy
        os.chmod(self._testing_rsa_path, 0o600)
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
    """Checks if DUT's power rail's voltage is okay.

    Returns:
      A dict of Whale INA & ADC points to their voltage measure (mV).

    Raises:
      BFTFixtureException if power rail is problematic.
    """
    inas = self._servo.MultipleGet(self._WHALE_INAS)
    result = {k: int(v) for k, v in inas.items()}

    # Servo returns a string of list of integers
    adc = ast.literal_eval(self._servo.Get(self._WHALE_CONTROL.ADC))
    for i in range(len(self._WHALE_ADC)):
      result[self._WHALE_ADC[i][0]] = adc[i] * self._WHALE_ADC[i][1]

    return result

  def CheckExtDisplay(self):
    raise NotImplementedError

  def GetFixtureId(self):
    raise NotImplementedError

  # pylint: disable=arguments-differ
  def ScanBarcode(self, saved_barcode_path=None):
    _UNSPECIFIED_ERROR = 'unspecified %s in BFT params'
    if not self._nuc_host:
      raise bft.BFTFixtureException(_UNSPECIFIED_ERROR % 'nuc_host')
    if not self._nuc_dut_serial_path and not saved_barcode_path:
      raise bft.BFTFixtureException(_UNSPECIFIED_ERROR % 'nuc_dut_serial_path')
    if not self._testing_rsa_path:
      raise bft.BFTFixtureException(_UNSPECIFIED_ERROR % 'testing_rsa_path')

    if not saved_barcode_path:
      saved_barcode_path = self._nuc_dut_serial_path

    ssh_command_base = ssh_utils.BuildSSHCommand(
        identity_file=self._testing_rsa_path)
    mlbsn = process_utils.SpawnOutput(
        ssh_command_base + [self._nuc_host, 'cat', saved_barcode_path])
    if not mlbsn:
      raise bft.BFTFixtureException('Unable to read barcode from %s:%s' %
                                    (self._nuc_host, saved_barcode_path))
    return mlbsn.strip()

  def IsLEDColor(self, color):
    if not self._color_sensor1:
      raise bft.BFTFixtureException(
          'Failed to check LED color: sensor is not initialized.')
    try:
      return self._color_sensor1.ReadColor() == color
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to check LED color. Reason %s' % e)

  def GetStatusColor(self):
    try:
      is_pass = self._servo.Get(self._WHALE_CONTROL.PASS_LED)
      is_fail = self._servo.Get(self._WHALE_CONTROL.FAIL_LED)

      for color, value in WhaleBFTFixture._STATUS_COLOR.items():
        if value == (is_pass, is_fail):
          return color
      # If no match, treat as OFF status
      return bft.BFTFixture.StatusColor.OFF
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException('Failed to get LED status. Reason: %s' % e)

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

  def ResetKeyboard(self):
    self._keyboard_emulator.Reset()

  def SimulateKeystrokes(self):
    self._keyboard_emulator.SimulateKeystrokes()

  def SimulateKeyPress(self, bitmask, duration_secs):
    try:
      self._keyboard_emulator.KeyPress(int(bitmask, 0), float(duration_secs))
    except ValueError as e:
      raise bft.BFTFixtureException('Failed to convert bitmask. Reason %s' % e)

  def SimulateButtonPress(self, button, duration_secs):
    logging.debug('press %s for %d seconds', button, duration_secs)

    whale_device = self._WHALE_DEVICE.get(button)
    if not whale_device:
      raise bft.BFTFixtureException('Unsupported device: ' + whale_device)
    try:
      if not duration_secs:  # set duration_secs 0 for long press
        self._servo.Set(whale_device, 'on')
      else:
        self._servo.Click(whale_device, duration_secs)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to press %s. Reason: %s' % (button, e))

  def SimulateButtonRelease(self, button):
    logging.debug('release %s', button)
    whale_device = self._WHALE_DEVICE.get(button)
    if not whale_device:
      raise bft.BFTFixtureException('Unsupported device: ' + whale_device)
    try:
      self._servo.Set(whale_device, 'off')
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to press %s. Reason: %s' % (button, e))

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
      return not self._servo.IsOn(self._FIXTURE_FEEDBACK.DUT_SENSOR)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to check if DUT in the fixture. Reason: ' + e)

  def IsBaseInFixture(self):
    try:
      return not self._servo.IsOn(self._FIXTURE_FEEDBACK.BASE_SENSOR)
    except servo_client.ServoClientError as e:
      raise bft.BFTFixtureException(
          'Failed to check if Base in the fixture. Reason: ' + e)

  def CoverStatus(self):
    status = self._servo.MultipleIsOn(self._FEEDBACKS)
    is_open = all([
        status[self._FIXTURE_FEEDBACK.FB1],
        status[self._FIXTURE_FEEDBACK.FB3],
        not status[self._FIXTURE_FEEDBACK.FB2],
        not status[self._FIXTURE_FEEDBACK.FB4], ])

    is_closed = all([
        not status[self._FIXTURE_FEEDBACK.FB1],
        not status[self._FIXTURE_FEEDBACK.FB3],
        status[self._FIXTURE_FEEDBACK.FB2],
        status[self._FIXTURE_FEEDBACK.FB4], ])

    if is_open:
      return self.Status.OPEN
    if is_closed:
      return self.Status.CLOSED
    return self.Status.CLOSING

  def TriggerScanner(self):
    try:
      self._servo.Click(self._WHALE_CONTROL.FIXTURE_NC,
                        duration_secs=0.3)
    except servo_client.ServoClientError as e:
      logging.exception('Failed to trigger scanner %s', e)
      raise bft.BFTFixtureException(
          'Failed to trigger scanner %s' % e)

  def StopFixture(self):
    """Stops fixture by opening cover."""
    logging.info('Stopping fixture...')

    # Disable battery first for safety.
    self._servo.Disable(self._WHALE_CONTROL.BATTERY)

    self._servo.Enable(self._WHALE_BUTTON.FIXTURE_STOP)
