# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.test.fixture.robot import robot

from cros.factory.external import serial


class SixDoFCalibrationRobot(robot.Robot):
  """Communication object for 6 DoF calibration robot.

  The robot is connected with a TCP/IP socket. With command as the following
  format:

    @CmdXX,parameter1,parameter2,...

    e.g., @Cmd02,10,10

  After sending command, robot sends back a 'OK' response after finishing the
  action.
  """

  _CMD_PREFIX = "@Cmd"

  CMD_POWER_ON = "00"
  CMD_POWER_OFF = "01"
  CMD_SET_SPEED = "02"
  CMD_SET_ACCELERATION = "03"
  CMD_LED = "04"
  CMD_MOVE_TO = "05"
  CMD_LOAD = "06"
  CMD_UNLOAD = "07"
  CMD_RESET = "15"

  # Movement type used for moving commands.
  # Move continuous without deceleration and acceleration.
  MOVEMENT_NOSTOP = "4"
  # Acceleration and deceleration in the second point then to destination.
  MOVEMENT_STOP = "6"

  LED_ON = "1"
  LED_OFF = "0"

  # The original position of the robot.
  POSITION_ORIGIN = "0"

  def __init__(self, url, speed, acceleration, timeout=30, log=True):
    """
    Args:
      speed: The required movement speed of the robot.
      acceleration: The required acceleration of the robot.
    """
    self._log = log
    self._url = url
    self._timeout = timeout
    self._speed = speed
    self._acceleration = acceleration
    self._serial = None

  def __del__(self):
    self.Disconnect()

  def Connect(self):
    self._serial = serial.serial_for_url(
        self._url, timeout=self._timeout, writeTimeout=self._timeout)

  def Disconnect(self):
    """Disconnects the socket connection."""
    if self._serial:
      self._serial.close()
    self._serial = None

  def _SendCommand(self, cmd, *args):
    """Sends command to the robot.

    Args:
      cmd: The command to be sent.
      args: Arguments to be sent with the command.
    """

    data = self._CMD_PREFIX + cmd
    if args:
      data += ',' + ','.join(args)

    if self._log:
      logging.info('Sending data %s to robot.', data)

    if self._serial.write(data) != len(data):
      raise robot.RobotException('Failed to send command.')

    res = self._serial.readline()
    if res.find('OK') == -1:
      raise robot.RobotException(
          'Unexpected data %s received from robot.' % res)

    if self._log:
      logging.info('Received from robot: %s', res)

  def SetMotor(self, power_on):
    if power_on:
      # This robot requires setting speed and acceleration after powering on.
      self._SendCommand(self.CMD_POWER_ON)
      self._SendCommand(self.CMD_SET_SPEED, *(['%d' % self._speed] * 2))
      self._SendCommand(self.CMD_SET_ACCELERATION,
                        *(['%d' % self._acceleration] * 4))
    else:
      # Make sure the robot is in unload position before power off.
      self.LoadDevice(False)
      self._SendCommand(self.CMD_POWER_OFF)

  def LoadDevice(self, load):
    self._SendCommand(self.CMD_LOAD if load else self.CMD_UNLOAD)

  def MoveTo(self, position):
    if isinstance(position, int):
      position = str(position)
    self._SendCommand(self.CMD_MOVE_TO, position, self.MOVEMENT_STOP)

  def SetLED(self, turn_on):
    """Turns ON / OFF the LED."""
    self._SendCommand(self.CMD_LED, self.LED_ON if turn_on else self.LED_OFF)
