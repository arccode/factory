#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=R0922

import factory_common # pylint: disable=W0611

from cros.factory.test.utils import Enum


class ECException(Exception):
  pass


class EC(object):
  """Basic EC interface class."""
  ChargeState = Enum(['CHARGE', 'IDLE', 'DISCHARGE'])

  # Auto fan speed.
  AUTO = 'auto'

  # Functions that are used in Goofy. Must be implemented.
  def GetTemperatures(self):
    """Gets a list of temperatures for various sensors.

    Returns:
      A list of int indicating the temperatures in Celsius.
      For those sensors which don't have readings, fill None instead.

    Raises:
      ECException when fail.
    """
    raise NotImplementedError

  def GetMainTemperatureIndex(self):
    """Gets the main index in temperatures list that should be logged.

    This is typically the CPU temperature.

    Returns:
      A int indicating the main temperature index.

    Raises:
      ECException when fail.
    """
    raise NotImplementedError

  def GetFanRPM(self):
    """Gets the fan RPM.

    Returns:
      A int indicating the fan RPM.

    Raises:
      ECException when fail.
    """
    raise NotImplementedError

  def GetVersion(self):
    """Gets the EC firmware version.

    Returns:
      A string of the EC firmware version.

    Raises:
      ECException when fail.
    """
    raise NotImplementedError

  def GetConsoleLog(self):
    """Gets the EC console log.

    Returns:
      A string containing EC console log.
    """
    raise NotImplementedError

  def SetChargeState(self, state):
    """Sets the charge state.

    Args:
      state: One of the three states in ChargeState.

    Raises:
       ECException when fail.
    """
    raise NotImplementedError

  # Optional functions. Implement them if you need them in your tests.
  def SetFanRPM(self, rpm):
    """Sets the target fan RPM.

    Args:
      rpm: Target fan RPM, or EC.AUTO for auto fan control.

    Raises:
      ECException when fail.
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
      ECException when fail.
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
       ECException when fail.
    """
    raise NotImplementedError

  def GetChargerCurrent(self):
    """Gets the amount of current we ask from charger.

    Returns:
      Interger value in mA.

    Raises:
      ECException when fail.
    """
    raise NotImplementedError

  def GetBatteryCurrent(self):
    """Gets the amount of current battery is charging/discharging at.

    Returns:
      Integer value in mA.

    Raises:
      ECException when fail.
    """
    raise NotImplementedError

  def Hello(self):
    """Says hello to EC.

    Raises:
      ECException if EC does not respond correctly.
    """
    raise NotImplementedError

  def GetBatteryDesignCapacity(self):
    """Gets battery's design capacity.

    Returns:
      Battery's design capacity in mAh.

    Raises:
      ECException if battery's design capacity cannot be obtained.
    """
    raise NotImplementedError
