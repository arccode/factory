# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Provides interfaces to interact with Whale BFT fixture."""

from __future__ import print_function
import logging
import os

import factory_common  # pylint: disable=W0611
import cros.factory.test.fixture.bft_fixture as bft
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
  # pylint: disable=E1101
  _WHALE_CONTROL = servo_client.WHALE_CONTROL
  _FIXTURE_FEEDBACK = servo_client.FIXTURE_FEEDBACK
  _FEEDBACKS = servo_client.WHALE_FEEDBACKS
  _WHALE_INAS = servo_client.WHALE_INAS

  # Mapping of Whale controlled device to Servo control.
  _WHALE_DEVICE = {
      bft.BFTFixture.Device.AUDIO_JACK  : _WHALE_CONTROL.AUDIO_PLUG,
      bft.BFTFixture.Device.BATTERY     : _WHALE_CONTROL.BATTERY,
      bft.BFTFixture.Device.LID_MAGNET  : _WHALE_CONTROL.ELECTRO_MAGNET,
      bft.BFTFixture.Device.C0_CC2_DUT  : _WHALE_CONTROL.DC,
      bft.BFTFixture.Device.C1_CC2_DUT  : _WHALE_CONTROL.OUTPUT_RESERVE_1}

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
        os.chmod(self._testing_rsa_path, 0600)
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
    result = dict((k, int(v)) for k, v in inas.iteritems())

    # Servo returns a string of list of integers
    adc = eval(self._servo.Get(self._WHALE_CONTROL.ADC))
    result['vdd_kbd_bl_dut'] = adc[0] * 32.5
    result['pp1200_ssd_dut'] = adc[1]
    result['vcore_dut'] = adc[2]
    result['pp600_vtt_dut'] = adc[3]
    result['pp3300_rtc_dut'] = adc[4] * 2
    result['pp1800_ssd_dut'] = adc[5]
    result['pp3300_usb_pd_dut'] = adc[6] * 2
    return result

  def CheckExtDisplay(self):
    raise NotImplementedError

  def GetFixtureId(self):
    raise NotImplementedError

  def ScanBarcode(self):
    _UNSPECIFIED_ERROR = 'unspecified %s in BFT params'
    if not self._nuc_host:
      raise bft.BFTFixtureException(_UNSPECIFIED_ERROR % 'nuc_host')
    if not self._nuc_dut_serial_path:
      raise bft.BFTFixtureException(_UNSPECIFIED_ERROR % 'nuc_dut_serial_path')
    if not self._testing_rsa_path:
      raise bft.BFTFixtureException(_UNSPECIFIED_ERROR % 'testing_rsa_path')

    ssh_command_base = ssh_utils.BuildSSHCommand(
        identity_file=self._testing_rsa_path)
    mlbsn = process_utils.SpawnOutput(
        ssh_command_base + [self._nuc_host, 'cat', self._nuc_dut_serial_path])
    if not mlbsn:
      raise bft.BFTFixtureException('Unable to read barcode from %s:%s' %
                                    (self._nuc_host, self._nuc_dut_serial_path))
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

      for color, value in WhaleBFTFixture._STATUS_COLOR.iteritems():
        if value == (is_pass, is_fail):
          return color
      else:
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

  def TriggerScanner(self):
    try:
      self._servo.Click(self._WHALE_CONTROL.FIXTURE_NC,
                        duration_secs=0.3)
    except servo_client.ServoClientError as e:
      logging.exception('Failed to trigger scanner %s', e)
      raise bft.BFTFixtureException(
          'Failed to trigger scanner %s' % e)
