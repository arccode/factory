#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides an interface for interacting with robot fixture.

This file is also an executable for users to communicate with the fixutre
under shell. It can be used to load an robot implementation and interact with
it.

For example::
  > robot.py cros.factory.test.fixture.robot.dummy_robot.DummyRobot

  What now> motor on
  What now> device unload
  What now> device load
  What now> move 0
  What now> motor off
  What now> quit

  Bye.
"""


import argparse
import json
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.test.fixture import utils as fixture_utils


class RobotException(Exception):
  pass


class Robot(object):
  """Interface of the robot arm fixture."""

  def Connect(self):
    """Connect to the robot fixture."""
    raise NotImplementedError

  def Disconnect(self):
    """Disconnect the robot fixture."""
    raise NotImplementedError

  def SetMotor(self, power_on):
    """Power on/off the robot motor.

    Args:
      power_on: True for powering on the robot motor, False otherwise.
    """
    raise NotImplementedError

  def LoadDevice(self, load):
    """Moves the robot between load/unload position and the start position.

    Args:
      load: If True, load the device and move the robot to the starting
            position. Otherwice, move the robot to the position for loading /
            unloading device.
    """
    raise NotImplementedError

  def MoveTo(self, position):
    """Moves the robot to the given position.

    Args:
      position: The id of the predefined point.
    """
    raise NotImplementedError

  def SetLED(self, turn_on):
    """Turns ON / OFF the LED.

    Args:
      turn_on: Turn on the LED if True.
    """
    raise NotImplementedError


def main(class_name, robot_params):
  cmd_parser = argparse.ArgumentParser(
      prog='', add_help=False,
      usage=('Supported commands are as following:\n'
             '    motor {on,off}\n'
             '    device {load,unload}\n'
             '    move <position>\n'
             '    led {on,off}\n'
             '    quit'))

  subparsers = cmd_parser.add_subparsers(dest='command')
  subparsers.add_parser('motor', add_help=False).add_argument(
      'choice', choices=['on', 'off'])
  subparsers.add_parser('device', add_help=False).add_argument(
      'choice', choices=['load', 'unload'])
  subparsers.add_parser('move', add_help=False).add_argument(
      'position', type=int)
  subparsers.add_parser('led', add_help=False).add_argument(
      'choice', choices=['on', 'off'])
  subparsers.add_parser('quit', add_help=False)

  cmd_parser.print_usage()

  robot = fixture_utils.CreateFixture(class_name, robot_params)
  robot.Connect()

  while True:
    cmd = raw_input('What now> ').strip().split()
    try:
      cmd_arg = cmd_parser.parse_args(cmd)
      if cmd_arg.command == 'motor':
        robot.SetMotor(cmd_arg.choice == 'on')
      elif cmd_arg.command == 'device':
        robot.LoadDevice(cmd_arg.choice == 'load')
      elif cmd_arg.command == 'move':
        robot.MoveTo(cmd_arg.position)
      elif cmd_arg.command == 'led':
        robot.SetLED(cmd_arg.choice == 'on')
      elif cmd_arg.command == 'quit':
        break
    except SystemExit:
      # When argparse fail, do nothing and ask for input again.
      pass

  print 'Disconnecting the robot...'
  robot.Disconnect()
  print 'Bye.'


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)

  parser = argparse.ArgumentParser()
  parser.add_argument(
      'config',
      type=str,
      help=('A config file to connect robot fixture. The file should contain a '
            'json dict with two keys: class_name and params. '
            'The class_name is the robot class to be used. The params is the '
            'arguments for the contructor. See dummy_robot.json '
            'for example.'))

  args = parser.parse_args()

  config = None

  with open(args.config) as f:
    config = json.loads(f.read())

  main(config['class_name'], config['params'])
