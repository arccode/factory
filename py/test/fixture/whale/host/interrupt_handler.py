#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles Whale's button click event."""

import argparse
import functools
import logging
import os
import re
import sys
import time

from cros.factory.test.fixture.whale import keyboard_emulator
from cros.factory.test.fixture.whale import serial_client
from cros.factory.test.fixture.whale import servo_client
from cros.factory.utils import gpio_utils
from cros.factory.utils import process_utils
from cros.factory.utils import ssh_utils
from cros.factory.utils import type_utils

ActionType = type_utils.Enum(['PUSH_NEEDLE', 'FIXTURE_STARTED'])

def TimeClassMethodDebug(func):
  """A decorator to log method running time on debug level."""
  @functools.wraps(func)
  def Wrapped(*args, **kwargs):
    logging.debug('Invoking %s()', func.__name__)
    start_time = time.time()
    result = func(*args, **kwargs)
    logging.debug('%s() finished in %.4f secs', func.__name__,
                  time.time() - start_time)
    return result
  return Wrapped


class InterruptHandler:
  """Waits for Whale's I/O expanders' interrupt and dispatches it.

  It connects to BeagleBone's servod and polld, where servod is used to get
  I/O expanders' input status and reset SR latches; polld is used to wait
  GPIO 7, the interrupt pin from Whale's I/O expanders.
  """
  # Shortcuts to Whale's button and control dict.
  _BUTTON = servo_client.WHALE_BUTTON
  _CONTROL = servo_client.WHALE_CONTROL
  _FIXTURE_FEEDBACK = servo_client.FIXTURE_FEEDBACK
  _PLANKTON_FEEDBACK = servo_client.PLANKTON_FEEDBACK
  _WHALE_DEBUG_MODE_EN = servo_client.WHALE_DEBUG_MODE_EN

  # List of buttons and feedbacks to scan.
  # Difference between button and feedback is: button is latched;
  #     no latch for feedback.
  _BUTTON_LIST = servo_client.WHALE_BUTTONS
  _FEEDBACK_LIST = servo_client.WHALE_FEEDBACKS

  # Buttons that operator can use (non debug mode).
  _OPERATOR_BUTTON_LIST = (_BUTTON.FIXTURE_START, _BUTTON.FIXTURE_STOP)

  # DUT sensor check list, add (FEEDBACK, Bool) to check if MLB exists.
  # example:
  # _DUT_SENSOR_CHECK_LIST = dict([
  #  (_FIXTURE_FEEDBACK.FB8, True),
  #  (_FIXTURE_FEEDBACK.FB9, False)])
  _DUT_SENSOR_CHECK_LIST = dict()

  _INPUT_LIST = _BUTTON_LIST + _FEEDBACK_LIST

  _INPUT_INTERRUPT_GPIO = 7

  # Used to avoid toggle battery too fast.
  _BATTERY_CEASE_TOGGLE_SECS = 1.0

  _FixtureState = type_utils.Enum(
      ['WAIT', 'CLOSED', 'ERR_CLOSING', 'CLOSING', 'OPENING'])
  # Fixture state to LED light and LCD message (green, red, message).
  _FixtureStateParams = {
      _FixtureState.WAIT: ('on', 'on', 'ready'),
      _FixtureState.CLOSED: ('off', 'off', 'closed'),
      _FixtureState.ERR_CLOSING: ('off', 'on', '!!no board inside!!'),
      _FixtureState.CLOSING: ('off', 'on', 'closing'),
      _FixtureState.OPENING: ('off', 'on', 'opening')}

  def __init__(self, host, polld_port, servod_port, dolphin_port, rpc_debug,
               polling_wait_secs):
    """Constructor.

    Args:
      host: BeagleBone's hostname or IP address.
      polld_port: port that polld listens. Set to None if not using polld.
      servod_port: port that servod listens.
      dolphin_port: port that dolphin server listens. Set to None if not using
          dolphin server.
      rpc_debug: True to enable XMLRPC debug message.
      polling_wait_secs: # seconds for polling button clicking event.
    """
    self._poll = gpio_utils.GpioManager(
        use_polld=polld_port is not None, host=host, tcp_port=polld_port,
        verbose=rpc_debug)

    self._dolphin = None
    if dolphin_port:
      self._dolphin = serial_client.SerialClient(
          host=host, tcp_port=dolphin_port, verbose=rpc_debug)

    self._servo = servo_client.ServoClient(host=host, port=servod_port,
                                           verbose=rpc_debug)

    self._polling_wait_secs = polling_wait_secs

    # Store last feedback value. The value is initialzed in the very first
    # ScanFeedback call.
    self._last_feedback = {}

    self._starting_fixture_action = None

    # Used to avoid toggle battery too fast.
    self._last_battery_toggle_time = time.time()

  @TimeClassMethodDebug
  def Init(self):
    """Resets button latch and records feedback value."""
    self._last_feedback = self._servo.MultipleIsOn(self._FEEDBACK_LIST)
    self._servo.MultipleSet([(self._CONTROL.LCM_CMD, 'clear'),
                             (self._CONTROL.LCM_TEXT, 'Initializing...')])
    self.ResetLatch()
    self.ResetInterrupt()
    self.ResetKeyboard()
    # Initial fixture state: cover open.
    self._HandleStopFixture(show_state=False)

    self._SetState(self._FixtureState.WAIT)

  def ResetKeyboard(self):
    keyboard = keyboard_emulator.KeyboardEmulator(self._servo)
    keyboard.SimulateKeystrokes()

  def _SetState(self, state):
    green, red, message = self._FixtureStateParams[state]
    self._servo.MultipleSet([(self._CONTROL.PASS_LED, green),
                             (self._CONTROL.FAIL_LED, red),
                             (self._CONTROL.LCM_CMD, 'clear'),
                             (self._CONTROL.LCM_TEXT, message)])

    self.ShowNucIpOnLED()

  def _IsMLBInFixture(self):
    """Checks MLB(s) is(are) inside the fixture.

    If the project has only one board, check DUT_SENSOR is enough. For two
    boards project, ex. lid and base boards, check DUT_SENSOR and BASE_SENSOR.

    Returns:
      True if MLB(s) is(are) inside the fixture; otherwise False.
    """
    if not self._DUT_SENSOR_CHECK_LIST:
      logging.info('No dut sensor...')
      return True

    dut_sensor_list = list(self._DUT_SENSOR_CHECK_LIST)
    dut_sensor_status = self._servo.MultipleIsOn(dut_sensor_list)

    return dut_sensor_status == self._DUT_SENSOR_CHECK_LIST

  @TimeClassMethodDebug
  def _HandleStopFixture(self, show_state=True):
    """Stop Fixture Step"""
    logging.info('Stopping fixture...')
    if show_state:
      self._SetState(self._FixtureState.OPENING)

    # Disable battery first for safety.
    self._servo.Disable(self._CONTROL.BATTERY)

    while True:
      feedback_status = self._servo.MultipleIsOn(self._FEEDBACK_LIST)

      if (not feedback_status[self._FIXTURE_FEEDBACK.FB1] or
          not feedback_status[self._FIXTURE_FEEDBACK.FB3]):
        self._servo.Disable(self._CONTROL.FIXTURE_PUSH_NEEDLE)
        continue

      self._starting_fixture_action = None
      logging.info('[Fixture stopped]')
      break
    self._SetState(self._FixtureState.WAIT)

  @TimeClassMethodDebug
  def _HandleStartFixtureFeedbackChange(self, feedback_status):
    """Processing Start Fixture feedback information"""
    if (self._starting_fixture_action is not None and
        self._starting_fixture_action != ActionType.FIXTURE_STARTED):
      # we are closing the fixture, check if we detect a hand
      if feedback_status[self._FIXTURE_FEEDBACK.FB5]:
        # detect hand, abort
        self._HandleStopFixture()
        return

    if self._servo.IsOn(self._BUTTON.FIXTURE_START):
      if (self._starting_fixture_action == ActionType.PUSH_NEEDLE and
          feedback_status[self._FIXTURE_FEEDBACK.FB2] and
          feedback_status[self._FIXTURE_FEEDBACK.FB4]):
        logging.info('[HandleStartFixture] fixture closed')
        self._starting_fixture_action = ActionType.FIXTURE_STARTED
        self._SetState(self._FixtureState.CLOSED)

  @TimeClassMethodDebug
  def _HandleStartFixture(self):
    """Start Fixture Step"""
    logging.info('[Fixture Start ...]')

    if self._starting_fixture_action == ActionType.FIXTURE_STARTED:
      logging.info('[HandleStartFixture] ACTION = FIXTURE_STARTED')
      return

    if self._last_feedback[self._FIXTURE_FEEDBACK.FB5]:
      logging.info('[HandleStartFixture] Detect Hands, stop..')
      return

    if self._starting_fixture_action is None:
      if not self._IsMLBInFixture():
        logging.info(
            '[HandleStartFixture] OOPS! Cannot close cover without MLBs')
        self._SetState(self._FixtureState.ERR_CLOSING)
        return
      self._ResetWhaleDeviceBeforeClosing()
      self._ResetDolphinDeviceBeforeClosing()
      self._starting_fixture_action = ActionType.PUSH_NEEDLE
      self._SetState(self._FixtureState.CLOSING)

    if self._starting_fixture_action == ActionType.PUSH_NEEDLE:
      logging.info('[HandleStartFixture] pushing needle')
      self._servo.Enable(self._CONTROL.FIXTURE_PUSH_NEEDLE)

  @TimeClassMethodDebug
  def _ResetWhaleDeviceBeforeClosing(self):
    """Resets devices on Whale if necessary before closing fixture."""
    # Release DUT CC2 pull-high
    self._servo.Disable(self._CONTROL.DC)
    self._servo.Disable(self._CONTROL.OUTPUT_RESERVE_1)

  @TimeClassMethodDebug
  def _ResetDolphinDeviceBeforeClosing(self):
    """Resets Dolphin if necessary before closing fixture."""
    if self._dolphin is None:
      return
    # Set dolphin to discharging mode, if dolphin is charging, DUT will fail to
    # boot up after battery connection.
    # Assuming all serial connections are connected to Dolphin.
    serial_amount = self._dolphin.GetSerialAmount()
    for serial_index in range(serial_amount):
      self._dolphin.Send(serial_index, 'usbc_action dev')

  @TimeClassMethodDebug
  def _ToggleBattery(self):
    """Toggles battery status.

    If battery is on, switches it to off and vise versa.
    """
    if (time.time() - self._last_battery_toggle_time <
        self._BATTERY_CEASE_TOGGLE_SECS):
      logging.debug('Toggle too fast, cease toggle for %f second.',
                    self._BATTERY_CEASE_TOGGLE_SECS)
      return

    new_battery_status = ('off' if self._servo.IsOn(self._CONTROL.BATTERY)
                          else 'on')
    logging.info('[Toggle battery to %s]', new_battery_status)
    self._servo.Set(self._CONTROL.BATTERY, new_battery_status)
    self._last_battery_toggle_time = time.time()

  @TimeClassMethodDebug
  def ScanButton(self):
    """Scans all buttons and invokes button click handler for clicked buttons.

    Returns:
      True if a button is clicked.
    """
    logging.debug('[Scanning button....]')
    status = self._servo.MultipleIsOn(self._BUTTON_LIST)

    if status[self._BUTTON.FIXTURE_STOP]:
      logging.info('Calling _HandleStopFixture because FIXTURE_STOP is True.')
      self._HandleStopFixture()
      # Disable stop button, and use 'i2cset' to set it back to input mode.
      self._servo.Disable(self._BUTTON.FIXTURE_STOP)
      process_utils.Spawn(['i2cset', '-y', '1', '0x77', '0x07', '0xff'])
      return True

    if (self._starting_fixture_action != ActionType.FIXTURE_STARTED and
        self._starting_fixture_action is not None and
        not status[self._BUTTON.FIXTURE_START]):
      logging.info('Calling _HandleStopFixture because FIXTURE_START is False.')
      self._HandleStopFixture()
      return False

    button_clicked = any(status.values())

    if not button_clicked:
      return False

    operator_mode = not self._servo.IsOn(self._WHALE_DEBUG_MODE_EN)
    for button, clicked in status.items():
      if not clicked:
        continue

      if operator_mode and button not in self._OPERATOR_BUTTON_LIST:
        logging.debug('Supress button %s click because debug mode is off.',
                      button)
        continue

      if button == self._BUTTON.FIXTURE_START:
        if self._starting_fixture_action == ActionType.FIXTURE_STARTED:
          logging.info('[START] ACTION = FIXTURE_STARTED')
        else:
          self._HandleStartFixture()
      elif button == self._BUTTON.RESERVE_1:
        self._ToggleBattery()

      logging.info('Button %s clicked', button)
    return button_clicked

  @TimeClassMethodDebug
  def ScanFeedback(self):
    """Scans all feedback and invokes handler for those changed feedback.

    Returns:
      True if any feedback value is clicked.
    """
    logging.debug('[Scanning feedback....]')
    feedback_status = self._servo.MultipleIsOn(self._FEEDBACK_LIST)
    feedback_changed = False
    for name, value in feedback_status.items():
      if self._last_feedback[name] == value:
        continue

      self._HandleStartFixtureFeedbackChange(feedback_status)
      logging.info('Feedback %s value changed to %r', name, value)
      self._last_feedback[name] = value
      feedback_changed = True

    return feedback_changed

  @TimeClassMethodDebug
  def ResetLatch(self):
    """Resets SR latch for buttons."""
    self._servo.Click(self._CONTROL.INPUT_RESET)

  @TimeClassMethodDebug
  def WaitForInterrupt(self):
    logging.debug('Polling interrupt (GPIO %d %s) for %r seconds',
                  self._INPUT_INTERRUPT_GPIO, self._poll.GPIO_EDGE_FALLING,
                  self._polling_wait_secs)
    if self._poll.Poll(self._INPUT_INTERRUPT_GPIO,
                       self._poll.GPIO_EDGE_FALLING,
                       self._polling_wait_secs):
      logging.debug('Interrupt polled')
    else:
      logging.debug('Polling interrupt timeout')

  @TimeClassMethodDebug
  def ResetInterrupt(self):
    """Resets I/O expanders' interrupt.

    We have four I/O expanders (TCA9539), three of them have inputs. As
    BeagleBone can only accept one interrupt, we cascade two expanders'
    (0x75, 0x77) INT to 0x76 input pins. So any input changes from 0x75, 0x76,
    0x77 will generate interrupt to BeagleBone.

    According to TCA9539 manual:
        "resetting the interrupt circuit is achieved when data on the port is
         changed to the original setting or data is read from the port that
         generated the interrupt. ... Because each 8-bit port is read
         independently, the interrupt caused by port 0 is not cleared by a read
         of port 1, or vice versa",
    to reset interrupt, we need to read each changing bit. However, as servod
    reads a byte each time we read an input pin, so we only need to read 0x77
    byte-0, byte-1, 0x75 byte-1, and 0x76 byte-0, byte-1, in sequence to reset
    INT. The reason to read in sequence is that we need to read 0x76 at last
    as 0x77 and 0x75 INT reset could change P02 and P03 pin in 0x76.
    """
    # Touch I/O expander 0x77 byte 0 & 1, 0x75 byte 1, 0x76 byte 0 & 1.
    # Note that we skip I/O expander 0x75 byte-0 as it contains no input
    # pin, won't trigger interrupt.
    self._servo.MultipleGet([
        self._FIXTURE_FEEDBACK.FB1, self._BUTTON.FIXTURE_START,
        self._PLANKTON_FEEDBACK.FB1, self._WHALE_DEBUG_MODE_EN,
        self._BUTTON.RESERVE_1])

  def Run(self):
    """Waits for Whale's button click interrupt and dispatches it."""
    while True:
      button_clicked = self.ScanButton()
      feedback_changed = self.ScanFeedback()
      # The reason why we don't poll interrupt right after reset latch is that
      # it might be possible that a button is clicked after latch is cleared
      # but before I/O expander is touched. In this case, the button is latched
      # but the interrupt is consumed (after touching I/O expander) so that the
      # following click of that button won't trigger interrupt again, and
      # polling is blocked.
      #
      # The solution is to read button again without waiting for interrupt.
      if button_clicked or feedback_changed:
        if button_clicked:
          self.ResetLatch()
        self.ResetInterrupt()
        continue

      self.WaitForInterrupt()

  def ShowNucIpOnLED(self):
    """Shows NUC dongle IP on LED second line"""
    nuc_host = '192.168.234.1'
    testing_rsa_path = '/usr/local/factory/misc/sshkeys/testing_rsa'
    get_dongle_eth_script = (
        'timeout 1s /usr/local/factory/py/test/fixture/get_dongle_eth.sh')

    # Make identity file less open to make ssh happy
    os.chmod(testing_rsa_path, 0o600)
    ssh_command_base = ssh_utils.BuildSSHCommand(
        identity_file=testing_rsa_path)

    try:
      interface = process_utils.SpawnOutput(
          ssh_command_base + [nuc_host, get_dongle_eth_script]).strip()
    except BaseException:
      interface = None

    if not interface:
      ip_address = 'dongle not found...'
    else:
      ifconfig_command = 'ifconfig %s' % interface
      ifconfig_result = process_utils.SpawnOutput(
          ssh_command_base + [nuc_host, ifconfig_command]).strip()
      ip_matcher = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ifconfig_result,
                             re.MULTILINE)
      if not ip_matcher:
        ip_address = 'dongle not found...'
      else:
        ip_address = ip_matcher.group(1)

    self._servo.MultipleSet([(self._CONTROL.LCM_ROW, 'r1'),
                             (self._CONTROL.LCM_TEXT, ip_address)])

def ParseArgs():
  """Parses command line arguments.

  Returns:
    args from argparse.parse_args().
  """
  description = (
      'Handle Whale button click event.'
  )

  parser = argparse.ArgumentParser(
      formatter_class=argparse.RawTextHelpFormatter, description=description)
  parser.add_argument('-d', '--debug', action='store_true', default=False,
                      help='enable debug messages')
  parser.add_argument('--rpc_debug', action='store_true', default=False,
                      help='enable debug messages for XMLRPC call')
  parser.add_argument('--nouse_dolphin', action='store_false', default=True,
                      dest='use_dolphin', help='whether to skip dolphin control'
                      ' (remote server). default: %(default)s')
  parser.add_argument('--use_polld', action='store_true', default=False,
                      help='whether to use polld (for polling GPIO port on '
                      'remote server) or poll local GPIO port, default: '
                      '%(default)s')
  parser.add_argument('--host', default='127.0.0.1', type=str,
                      help='hostname of server, default: %(default)s')
  parser.add_argument('--dolphin_port', default=9997, type=int,
                      help='port that dolphin_server listens, default: '
                      '%(default)d')
  parser.add_argument('--polld_port', default=9998, type=int,
                      help='port that polld listens, default: %(default)d')
  parser.add_argument('--servod_port', default=9999, type=int,
                      help='port that servod listens, default: %(default)d')
  parser.add_argument('--polling_wait_secs', default=5, type=int,
                      help=('# seconds for polling button clicking event, '
                            'default: %(default)d'))

  return parser.parse_args()


def main():
  args = ParseArgs()
  logging.basicConfig(
      level=logging.DEBUG if args.debug else logging.INFO,
      format='%(asctime)s - %(levelname)s - %(message)s')

  polld_port = args.polld_port if args.use_polld else None
  dolphin_port = args.dolphin_port if args.use_dolphin else None

  handler = InterruptHandler(args.host, polld_port, args.servod_port,
                             dolphin_port, args.rpc_debug,
                             args.polling_wait_secs)
  handler.Init()
  handler.Run()


if __name__ == '__main__':
  try:
    main()
  except KeyboardInterrupt:
    sys.exit(0)
  except gpio_utils.GpioManagerError as e:
    sys.stderr.write(str(e) + '\n')
    sys.exit(1)
