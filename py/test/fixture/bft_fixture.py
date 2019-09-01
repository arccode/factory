#!/usr/bin/env python2

# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides an interface for DUT to interact with BFT fixture.

Also provides factory function CreateBFTFixture() to import specific
BFTFixture module, instantiate it, and connect to the fixture.

It is also an executable for users to communicate with BFT fixutre
under DUT shell. For example::
  bft_fixture Ping
  bft_fixture Engage AC_ADAPTER
  bft_fixture Disengage AC_ADAPTER
  bft_fixture IsLEDColor RED
  bft_fixture SetStatusColor GREEN
  bft_fixture SetStatusColor OFF
  bft_fixture SimulateKeystrokes
  bft_fixture SimulateKeyPress [bitmask] [period_secs]
  bft_fixture SetLcmText ROW[0-3] [message]
  bft_fixture IssueLcmCommand [CLEAR | HOME | BACKLIGHT_ON | BACKLIGHT_OFF]

  If you are not running on DUT or bft.conf is missing in the DUT:
    /usr/local/factory/py/test/fixture/bft.conf
  You may specify config like:
  bft_fixture --config whale/bft.conf Ping
"""

import argparse
import logging
import os

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils


TEST_ARG_HELP = """A dictionary with the following items:

  ``class_name``
    Fully-qualified class name of the BFTFixture implementation
    to use.

  ``params``
    A dictionary of parameters for the BFTFixture class's ``Init()``
    method.

The default value of ``None`` means that no BFT fixture is used.
"""


class BFTFixtureException(Exception):
  pass


class BFTFixture(object):
  """Base class of BFT (Board Function Test) fixture.

  It defines interfaces for DUT (Device Under Test) to interact with
  BFT fixture.

  Methods for this class will raise BFTFixtureException if a failure occurs.
  """
  SystemStatus = type_utils.Enum(['BACKLIGHT'])
  Status = type_utils.Enum(['OFF', 'ON', 'OPEN', 'CLOSING', 'CLOSED'])

  # A subset of cros.factory.device.led.LED.Color.
  LEDColor = type_utils.Enum(['RED', 'GREEN', 'YELLOW', 'BLUE', 'OFF'])

  StatusColor = type_utils.Enum(['RED', 'GREEN', 'OFF'])
  Device = type_utils.Enum([
      'AC_ADAPTER', 'AUDIO_JACK', 'EXT_DISPLAY', 'LID_MAGNET',
      'USB_0', 'USB_1', 'USB_2', 'BATTERY',
      'C0_CC2_DUT', 'C1_CC2_DUT', 'PWR_BUTTON',
      'LID_HALL_MAGNET', 'BASE_HALL_MAGNET', 'BASE_CHARGER',
      'VOLU_BUTTON', 'VOLD_BUTTON',
      # Plankton-Raiden fixture devices.
      'CHARGE_5V', 'CHARGE_12V', 'CHARGE_20V',
      'USB2', 'USB3', 'DP', 'ADB_HOST', 'DEFAULT'])

  # LCM enumeration.
  LcmCommand = type_utils.Enum([
      'BACKLIGHT_OFF', 'BACKLIGHT_ON', 'CLEAR', 'HOME'])
  LcmRow = type_utils.Enum(['ROW0', 'ROW1', 'ROW2', 'ROW3'])

  def Init(self, **kwargs):
    """Initializes connection with fixture."""
    raise NotImplementedError

  def Disconnect(self):
    """Disconnects fixture.

    Closes the connection to the fixture.
    """
    raise NotImplementedError

  def GetSystemStatus(self, component):
    """Gets DUT system status.

    The fixture can probe certain DUT's components' status.

    Args:
      component: A DUT's component defined in SystemStatus Enum.

    Returns:
      Status Enum.
    """
    raise NotImplementedError

  def GetDeviceStatus(self, device):
    """Gets a fixture controlled device's status.

    Args:
      device: BFT controlled device defined in Device Enum.

    Returns:
      Status Enum.
    """
    raise NotImplementedError

  def SetDeviceEngaged(self, device, engage):
    """Engages / disengages a device.

    If engage, the fixture plugs/connects the device into the DUT; otherwise,
    it unplugs/disconnects the device.

    Args:
      device: BFT controlled device defined in Device.
      engage: True to engage device; False to disengage.
    """
    raise NotImplementedError

  def Ping(self):
    """Pings the BFT fixture.

    Raises:
      BFTFixtureException when ping fails.
    """
    raise NotImplementedError

  def CheckPowerRail(self):
    """Checks if DUT's power rail's voltage is okay.

    Raises:
      BFTFixtureException if power rail is problematic.
    """
    raise NotImplementedError

  def CheckExtDisplay(self):
    """Checks if external display shows screen as expected.

    Raises:
      BFTFixtureException if the fixture didn't see the expected screen.
    """
    raise NotImplementedError

  def GetFixtureId(self):
    """Gets fixture ID.

    Each fixture has its identification number. We use it to collect the ID
    to figure out if a fixture has a higher error rate for certain test case.

    Returns:
      Fixture ID (integer).
    """
    raise NotImplementedError

  def ScanBarcode(self):
    """Triggers barcode scanner.

    In BFT fixture it has barcode scanner to scan motherboard ID.
    Once the barcode scanner is triggered, the barcode will be sent
    as a keyboard sequence. It is DUT test program's responsibility
    to process the scanned result.
    """
    raise NotImplementedError

  def SimulateKeystrokes(self):
    """Triggers keyboard scanner.

    In BFT fixture it has a keyboard scanner. Insead of pressing every key
    in a keyboard, we attach the DUT with a keyboard scanner, which sends
    a sequence of keystrokes that covers all keyboard scan line. It is
    DUT test program's responsibility to receive and verify the keystroke
    sequence.
    """
    raise NotImplementedError

  def IsLEDColor(self, color):
    """Asks fixture to check DUT board's LED with color specified.

    Args:
      color: color defined in LEDColor.

    Returns:
      True if LED's color is correct; False otherwise.
    """
    raise NotImplementedError

  def GetStatusColor(self):
    """Gets the color of status indicator.

    Returns:
      LEDColor Enum.
    """
    raise NotImplementedError

  def SetStatusColor(self, color):
    """Sets the fixture's status indicator to a given color.

    Args:
      color: color defined in StatusColor.
    """
    raise NotImplementedError

  def SimulateKeyPress(self, key, duration_secs):
    """Simulates keyboard key press for a period of time."""
    raise NotImplementedError

  def ResetKeyboard(self):
    """Reset keyboard device."""
    raise NotImplementedError

  def SimulateButtonPress(self, button, duration_secs):
    """Simulates button press for a period of time.

    Args:
      button: button to press
      duration_secs: pressing length, in seconds.  If it is 0, will press
        indefinitely until released by "SimulateButtonRelease".
    """
    raise NotImplementedError

  def SimulateButtonRelease(self, button):
    """Simulates button release.

    This is used to release a button that is pressed by:
      self.SimulateButtonPress(button, 0)
    """
    raise NotImplementedError

  def SetLcmText(self, row, message):
    """Shows a message to a given row of LCM.

    Args:
      row: row number defined in LcmRow.
      message: a message to show on LCM.
    """
    raise NotImplementedError

  def IssueLcmCommand(self, action):
    """Issues a command to LCM.

    Args:
      action: action defined in LcmCommand.
    """
    raise NotImplementedError

  def IsDUTInFixture(self):
    """Is DUT in BFT fixture?

    Returns:
       True if DUT is in BFT fixture.
    """
    raise NotImplementedError

  def IsBaseInFixture(self):
    """Is Base in BFT fixture?

    Returns:
       True if Base is in BFT fixture.
    """
    raise NotImplementedError

  def CoverStatus(self):
    """Gets the status of fixture cover.

    Returns:
      Status: one of OPEN, CLOSING, CLOSED.
    """
    raise NotImplementedError

  def TriggerScanner(self):
    """Turn the scanner on and off."""
    raise NotImplementedError

  def SetUSBHubChargeStatus(self, enable):
    """Sets Plankton charge or not to device on USB hub.

    Args:
      enable: True for charging; False for not charging.
    """
    raise NotImplementedError

  def ResetUSBHub(self, wait_before_reset_secs=1, wait_after_reset_secs=1):
    """Toggles reset signal of Plankton USB Hub.

    Args:
      wait_before_reset_secs: Waiting seconds before reset sequence.
      wait_after_reset_secs: Waiting seconds after reset sequence.
    """
    raise NotImplementedError

  def ReadINAValues(self):
    """Sends INA command and read back voltage and current value.

    Returns:
      A dict which contains 'voltage' (in mV) and 'current' (in mA) data.
    """
    raise NotImplementedError


def CreateBFTFixture(class_name, params):
  """Initializes a BFT fixture instance.

  Imports a BFT fixture module based on class_name and initializes the
  instance using params.

  Args:
    class_name: fixture's import path + module name. For example,
        "cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture".
    params: a dict of params for Init().

  Returns:
    An instance of the specified BFT fixture implementation.
  """
  module, cls = class_name.rsplit('.', 1)
  fixture = getattr(__import__(module, fromlist=[cls]), cls)()
  fixture.Init(**params)
  return fixture


def main():
  """Command line interface for controlling BFT fixture directly.

  Refer module comment for usage.
  """
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(description='BFT command line tool.')
  parser.add_argument(
      '--config',
      default='/usr/local/factory/py/test/fixture/bft.conf',
      help=('A config file to connect BFT fixture. If default bft.conf is not '
            'found, a DummyBFTFixture is used.'))

  subparsers = parser.add_subparsers(dest='command')
  support_devices = sorted(BFTFixture.Device)
  parser_engage = subparsers.add_parser(
      'Engage', help='Engage a device. -h for more help.')
  parser_engage.add_argument('device', choices=support_devices,
                             help='Device to engage.')

  parser_disengage = subparsers.add_parser(
      'Disengage', help='Disengage a device. -h for more help.')
  parser_disengage.add_argument('device', choices=support_devices,
                                help='Device to disengage.')

  parser_device_status = subparsers.add_parser(
      'DeviceStatus', help='Get status of a device. -h for more help.')
  parser_device_status.add_argument('device', choices=support_devices,
                                    help='Device to get status.')

  parser_system_status = subparsers.add_parser(
      'SystemStatus',
      help='Get status of a component in DUT. -h for more help.')
  parser_system_status.add_argument(
      'component', choices=sorted(BFTFixture.SystemStatus),
      help='A DUT component (defined in SystemStatus) to get status.')

  parser_is_led_color = subparsers.add_parser(
      'IsLEDColor', help='Check LED color. -h for more help.')
  parser_is_led_color.add_argument('color',
                                   choices=sorted(BFTFixture.LEDColor),
                                   help='Color to inspect.')

  parser_set_status_color = subparsers.add_parser(
      'SetStatusColor', help='Set status color indicator. -h for more help.')
  parser_set_status_color.add_argument('color',
                                       choices=sorted(BFTFixture.StatusColor),
                                       help='Status color to set.')

  subparsers.add_parser('ResetKeyboard', help='Reset keyboard device.')

  subparsers.add_parser('SimulateKeystrokes',
                        help='Trigger all row-column crossings in sequence.')

  parser_simulate_key_press = subparsers.add_parser(
      'SimulateKeyPress',
      help='Simulate pressing single or multiple key(s) for a period of time.')
  parser_simulate_key_press.add_argument('bitmask',
                                         help='16-bit bitmask of key states.')
  parser_simulate_key_press.add_argument('period_secs',
                                         type=float,
                                         help='Key pressed duration.')

  parser_set_lcm_text = subparsers.add_parser(
      'SetLcmText', help='Show a message on LCM. -h for more help.')
  parser_set_lcm_text.add_argument('row_number',
                                   choices=sorted(BFTFixture.LcmRow),
                                   help='Row number to set.')
  parser_set_lcm_text.add_argument('message',
                                   help='Message to show.')

  parser_issue_lcm_command = subparsers.add_parser(
      'IssueLcmCommand', help='Issue a command to LCM. -h for more help.')
  parser_issue_lcm_command.add_argument(
      'action', choices=sorted(BFTFixture.LcmCommand),
      help='Action to execute.')

  parser_set_usb_hub_charge = subparsers.add_parser(
      'SetUSBHubChargeStatus', help='Set Plankton USB hub charge status.')
  parser_set_usb_hub_charge.add_argument(
      'enable', type=int, help='Set 1 to enable, 0 to disable.')

  subparsers.add_parser('CheckExtDisplay', help='Check external display.')
  subparsers.add_parser('CheckPowerRail', help='Check power rail.')
  subparsers.add_parser('GetFixtureId', help='Get fixture ID.')
  subparsers.add_parser('Ping', help='Ping fixture.')
  subparsers.add_parser('ScanBarcode', help='Trigger barcode scanner.')
  subparsers.add_parser('ResetUSBHub', help='Reset Plankton USB hub')
  subparsers.add_parser(
      'ReadINAValues',
      help='Read current (mA) and voltage (mV) from Plankton INA.')

  args = parser.parse_args()

  fixture = None

  fixture_param = {
      'class_name':
          'cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture',
      'params': {}
  }
  if os.path.exists(args.config):
    with open(args.config, 'r') as config_file:
      fixture_param = yaml.load(config_file)

  logging.info('CreateBFTFixture(%r, %r)', fixture_param['class_name'],
               fixture_param['params'])
  fixture = CreateBFTFixture(**fixture_param)

  command = args.command
  if command == 'Engage' or command == 'Disengage':
    print '%s %s' % (command, args.device)
    fixture.SetDeviceEngaged(args.device,
                             True if command == 'Engage' else False)
  elif command == 'DeviceStatus':
    device = args.device
    print 'GetDeviceStatus(%s): %s' % (device, fixture.GetDeviceStatus(device))
  elif command == 'SystemStatus':
    component = args.component
    print 'GetSystemStatus(%s): %s' % (device,
                                       fixture.GetSystemStatus(component))
  elif command == 'IsLEDColor':
    color = args.color
    print 'IsLEDColor(%s): %s' % (color, fixture.IsLEDColor(color))
  elif command == 'SetStatusColor':
    color = args.color
    fixture.SetStatusColor(color)
    print 'SetStatusColor(%s)' % color
  elif command == 'ResetKeyboard':
    fixture.ResetKeyboard()
  elif command == 'SimulateKeystrokes':
    fixture.SimulateKeystrokes()
  elif command == 'SimulateKeyPress':
    bitmask = args.bitmask
    period_secs = args.period_secs
    print 'SimulateKeyPress(%s, %s)' % (bitmask, period_secs)
    fixture.SimulateKeyPress(bitmask, period_secs)
  elif command == 'SetLcmText':
    row_number = args.row_number
    message = args.message
    print 'SetLcmText(%s, %s)' % (row_number, message)
    fixture.SetLcmText(row_number, message)
  elif command == 'IssueLcmCommand':
    action = args.action
    print 'IssueLcmCommand(%s)' % (action)
    fixture.IssueLcmCommand(action)
  elif command == 'SetUSBHubChargeStatus':
    enable = args.enable
    print 'SetUSBHubChargeStatus(%r)' % (enable)
    fixture.SetUSBHubChargeStatus(enable)
  else:
    print getattr(fixture, command)()


if __name__ == '__main__':
  main()
