# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic board specific interface."""


# pylint: disable=R0922

import factory_common  # pylint: disable=W0611
from cros.factory.system.power import Power
from cros.factory.test.utils import Enum


class BoardException(Exception):
  """Exception for Board class."""
  pass


class Board(object):
  """Abstract interface for board-specific functionality.

  This class provides an interface for board-specific functionality,
  such as forcing device charge state, forcing fan speeds, and
  observing on-board temperature sensors.  In general, these behaviors
  are implemented with low-level commands such as ``ectool``, so
  there may be no standard interface to them (e.g., via the ``/sys``
  filesystem).

  To obtain a :py:class:`cros.factory.system.board.Board` object for
  the device under test, use the
  :py:func:`cros.factory.system.GetBoard` function.

  Implementations of this interface should be in the
  :py:mod:`cros.factory.board` package.  One such implementation,
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard`, mostly
  implements these behaviors using ``ectool``.  It is mostly concrete
  but may be further subclassed as necessary.

  In general, this class is only for functionality that may need to be
  implemented separately on a board-by-board basis.  If there is a
  standard system-level interface available for certain functionality
  (e.g., using a Python API, a binary available on all boards, or
  ``/sys``) then it should not be in this class, but rather wrapped in
  a class in the :py:mod:`cros.factory.system` module, or in a utility
  method in :py:mod:`cros.factory.utils`.  See
  :ref:`board-api-extending`.

  All methods may raise a :py:class:`BoardException` on failure, or a
  :py:class:`NotImplementedException` if not implemented for this board.
  """
  ChargeState = Enum(['CHARGE', 'IDLE', 'DISCHARGE'])
  """An enumeration of possible charge states.

  - ``CHARGE``: Charge the device as usual.
  - ``IDLE``: Do not charge the device, even if connected to mains.
  - ``DISCHARGE``: Force the device to discharge.
  """

  LEDColor = Enum(['AUTO', 'OFF', 'RED', 'GREEN', 'BLUE', 'YELLOW', 'WHITE'])
  """Charger LED colors.

  - ``AUTO``: Use the default logic to select the LED color.
  - ``OFF``: Turn the LED off.
  - others: The respective colors.
  """

  LEDIndex = Enum(['POWER', 'BATTERY', 'ADAPTER'])
  """LED names.

  - ``POWER``: Power LED.
  - ``BATTERY``: Battery LED.
  - ``ADAPTER``: Adapter LED.
  """

  AUTO = 'auto'
  """Constant representing automatic fan speed."""

  # Functions that are used in Goofy. Must be implemented.

  def __init__(self):
    # Overrides methods in Power using board-specific Power class
    self.power = Power()

  def GetTemperatures(self):
    """Gets a list of temperatures for various sensors.

    Returns:
      A list of int indicating the temperatures in Celsius.
      For those sensors which don't have readings, fill None instead.
    """
    raise NotImplementedError

  def GetMainTemperatureIndex(self):
    """Gets the main index in temperatures list that should be logged.

    This is typically the CPU temperature.

    Returns:
      A int indicating the main temperature index.
    """
    raise NotImplementedError

  def GetFanRPM(self):
    """Gets the fan RPM.

    Returns:
      A list of int indicating the RPM of each fan.
    """
    raise NotImplementedError

  def GetECVersion(self):
    """Gets the EC firmware version.

    Returns:
      A string of the EC firmware version.
    """
    raise NotImplementedError

  def GetPDVersion(self):
    """Gets the PD firmware version.

    Returns:
      A string of the PD firmware version.
    """
    raise NotImplementedError

  def GetMainFWVersion(self):
    """Gets the main firmware version.

    Returns:
      A string of the main firmware version.
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
    """
    raise NotImplementedError

  # Optional functions. Implement them if you need them in your tests.
  def GetTemperatureSensorNames(self):
    """Gets a list of names for temperature sensors.

    Returns:
      A list of str containing the names of all temperature sensors.
      The order must be the same as the returned list from GetTemperatures().
    """
    raise NotImplementedError

  def SetFanRPM(self, rpm):
    """Sets the target fan RPM.

    Args:
      rpm: Target fan RPM, or Board.AUTO for auto fan control.
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
    """
    raise NotImplementedError

  def I2CWrite(self, port, addr, reg, value):
    """Writes 16-bit value to I2C bus.

    Args:
      port: I2C port ID.
      addr: I2C slave address.
      reg: Slave register address.
      value: 16-bit value to write.
    """
    raise NotImplementedError

  def GetChargerCurrent(self):
    """Gets the amount of current we ask from charger.

    Returns:
      Interger value in mA.
    """
    raise NotImplementedError

  def GetBatteryCurrent(self):
    """Gets the amount of current battery is charging/discharging at.

    Returns:
      Integer value in mA.
    """
    raise NotImplementedError

  def ProbeEC(self):
    """Says hello to EC.
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
      The output of ectool powerinfo, like::

        AC Voltage: 5143 mV
        System Voltage: 11753 mV
        System Current: 1198 mA
        System Power: 14080 mW
        USB Device Type: 0x20010
        USB Current Limit: 2958 mA

      It can be further parsed by
      :py:func:`cros.factory.utils.string_utils.ParseDict` into a
      dict.

    Raises:
      BoardException if power information cannot be obtained.
    """
    raise NotImplementedError

  def GetBoardVersion(self):
    """Gets the version of the board (MLB).

    Returns:
      A string of the version of the MLB board, like::

        Proto2B
        EVT
        DVT

    Raises:
      BoardException if board version cannot be obtained.
    """
    raise NotImplementedError
