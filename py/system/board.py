#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic board specific interface."""


# pylint: disable=R0922
import collections

import factory_common # pylint: disable=W0611

from cros.factory.system.power import Power
from cros.factory.test.utils import Enum


class BoardException(Exception):
  """Exception for Board class."""
  pass


class Board(object):
  """Basic board specific interface class."""
  ChargeState = Enum(['CHARGE', 'IDLE', 'DISCHARGE'])

  LEDColor = Enum(['AUTO', 'OFF', 'RED', 'GREEN', 'BLUE', 'YELLOW', 'WHITE'])

  # Auto fan speed.
  AUTO = 'auto'

  # Partitions that factory cares on a factory-installed device.
  Partition = collections.namedtuple('Partition', ['name', 'index'])
  Partition.STATEFUL = Partition('STATEFUL', 1)
  Partition.FACTORY_KERNEL = Partition('FACTORY_KERNEL', 2)
  Partition.FACTORY_ROOTFS = Partition('FACTORY_ROOTFS', 3)
  Partition.RELEASE_KERNEL = Partition('RELEASE_KERNEL', 4)
  Partition.RELEASE_ROOTFS = Partition('RELEASE_ROOTFS', 5)

  # Functions that are used in Goofy. Must be implemented.
  def __init__(self):
    # Overrides methods in Power using board-specific Power class
    self.power = Power()

  def GetTemperatures(self):
    """Gets a list of temperatures for various sensors.

    Returns:
      A list of int indicating the temperatures in Celsius.
      For those sensors which don't have readings, fill None instead.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def GetMainTemperatureIndex(self):
    """Gets the main index in temperatures list that should be logged.

    This is typically the CPU temperature.

    Returns:
      A int indicating the main temperature index.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def GetFanRPM(self):
    """Gets the fan RPM.

    Returns:
      A int indicating the fan RPM.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def GetECVersion(self):
    """Gets the EC firmware version.

    Returns:
      A string of the EC firmware version.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def GetMainFWVersion(self):
    """Gets the main firmware version.

    Returns:
      A string of the main firmware version.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def GetECConsoleLog(self):
    """Gets the EC console log.

    Returns:
      A string containing EC console log.
    """
    raise NotImplementedError

  def GetECPanicInfo(self):
    """Gets the EC panic info.

    Returns:
      A string of EC panic info.
    """
    raise NotImplementedError

  def SetChargeState(self, state):
    """Sets the charge state.

    Args:
      state: One of the three states in ChargeState.

    Raises:
       BoardException when fail.
    """
    raise NotImplementedError

  # Optional functions. Implement them if you need them in your tests.
  def GetTemperatureSensorNames(self):
    """Gets a list of names for temperature sensors.

    Returns:
      A list of str containing the names of all temperature sensors.
      The order must be the same as the returned list from GetTemperatures().

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def SetFanRPM(self, rpm):
    """Sets the target fan RPM.

    Args:
      rpm: Target fan RPM, or Board.AUTO for auto fan control.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def I2CRead(self, port, addr, reg):
    """Reads 16-bit value from I2C bus.

    Args:
      port: I2C port ID.
      addr: I2C slave address.
      reg: Slave register address.

    Returns:
      Integer value read from slave.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def I2CWrite(self, port, addr, reg, value):
    """Writes 16-bit value to I2C bus.

    Args:
      port: I2C port ID.
      addr: I2C slave address.
      reg: Slave register address.
      value: 16-bit value to write.

    Raises:
       BoardException when fail.
    """
    raise NotImplementedError

  def GetChargerCurrent(self):
    """Gets the amount of current we ask from charger.

    Returns:
      Interger value in mA.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def GetBatteryCurrent(self):
    """Gets the amount of current battery is charging/discharging at.

    Returns:
      Integer value in mA.

    Raises:
      BoardException when fail.
    """
    raise NotImplementedError

  def ProbeEC(self):
    """Says hello to EC.

    Raises:
      BoardException if EC does not respond correctly.
    """
    raise NotImplementedError

  def GetBatteryDesignCapacity(self):
    """Gets battery's design capacity.

    Returns:
      Battery's design capacity in mAh.

    Raises:
      BoardException if battery's design capacity cannot be obtained.
    """
    raise NotImplementedError

  def SetLEDColor(self, color, led_name='battery', brightness=100):
    """Sets LED color.

    Args:
      color: LED color of type LEDColor enum.
      led_name: target LED name.
      brightness: LED brightness in percentage [0, 100].
          If color is 'auto' or 'off', brightness is ignored.
    """
    raise NotImplementedError

  def GetPowerInfo(self):
    """Gets power information.

    Returns:
      The output of ectool powerinfo like
      AC Voltage: 5143 mV
      System Voltage: 11753 mV
      System Current: 1198 mA
      System Power: 14080 mW
      USB Device Type: 0x20010
      USB Current Limit: 2958 mA
      It can be further parsed by string_utils.ParseDict into a dict.

    Raises:
      BoardException if power information cannot be obtained.
    """
    raise NotImplementedError

  def GetRootDev(self):
    """Gets root block device."""
    raise NotImplementedError

  def GetPartition(self, partition):
    """Gets partition path for given Board.Partition."""
    raise NotImplementedError
