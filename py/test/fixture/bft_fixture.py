#!/usr/bin/python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides an interface for DUT to interact with BFT fixture.

Also provides factory function CreateBFTFixture() to import specific
BFTFixture module, instantiate it, and connect to the fixture.

It is also an executable for users to communicate with BFT fixutre
under DUT shell.
"""

import argparse
import logging
import os
import yaml

import factory_common # pylint: disable=W0611
from cros.factory.test.utils import Enum


class BFTFixtureException(Exception):
  pass


class BFTFixture(object):
  """Base class of BFT (Board Function Test) fixture.

  It defines interfaces for DUT (Device Under Test) to interact with
  BFT fixture.

  Methods for this class will raise BFTFixtureException if a failure occurs.
  """

  # A subset of factory.system.board.Board.LEDColor.
  SystemStatus = Enum(['BACKLIGHT'])
  Status = Enum(['OFF', 'ON'])
  LEDColor = Enum(['RED', 'GREEN', 'YELLOW', 'OFF'])
  StatusColor = Enum(['RED', 'GREEN'])
  Device = Enum(['AC_ADAPTER', 'AUDIO_JACK', 'EXT_DISPLAY', 'LID_MAGNET',
                 'USB_0', 'USB_1', 'USB_2'])

  def Init(self, **kwargs):
    """Initializes connection with fixture."""
    raise NotImplementedError

  def Disconnect(self):
    """Disconnects fixture.

    Closes the connection to the fixture.
    """
    raise NotImplementedError

  def GetSystemStatus(self, status):
    raise NotImplementedError

  def SetDeviceEngaged(self, device, engage):
    """Engage a device.

    If engage, the fixture plugs the device into the DUT; otherwise,
    it unplugs the device.

    Args:
      device: BFT controlled device defined in Device.
      engage: True to engage device; False to disengage.
    """
    raise NotImplementedError

  def Ping(self):
    """Pings the BFT fixture.

    If ping fails, raises BFTFixtureException.
    """
    raise NotImplementedError

  def CheckPowerRail(self):
    """Checks if DUT's power rail's voltage is okay.

    Raises BFTFixtureException if power rail is problematic.
    """
    raise NotImplementedError

  def CheckExtDisplay(self):
    """Checks if external display shows screen as expected.

    Raises BFTFixtureException if the fixture didn't see the expected screen.
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

  def SetStatusColor(self, color):
    """Sets the fixture's status indicator to a given color.

    Args:
      color: color defined in StatusColor.
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

  parser_is_led_color = subparsers.add_parser(
      'IsLEDColor', help='Check LED color. -h for more help.')
  parser_is_led_color.add_argument('color',
                                   choices=sorted(BFTFixture.LEDColor),
                                   help='Color to inspect.')

  subparsers.add_parser('CheckExtDisplay', help='Check external display.')
  subparsers.add_parser('CheckPowerRail', help='Check power rail.')
  subparsers.add_parser('GetFixtureId', help='Get fixture ID.')
  subparsers.add_parser('Ping', help='Ping fixture.')
  subparsers.add_parser('ScanBarcode', help='Trigger barcode scanner.')
  subparsers.add_parser('SimulateKeystrokes', help='Trigger keyboard scanner.')

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
  elif command == 'IsLEDColor':
    color = args.color
    print 'IsLEDColor(%s): %s' % (color, fixture.IsLEDColor(color))
  else:
    getattr(fixture, command)()


if __name__ == "__main__":
  main()
