#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System thermal provider.

This module provides reading and setting system thermal sensors and controllers.
"""

from __future__ import print_function

import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


class Thermal(component.DUTComponent):
  """System module for thermal control (temperature sensors, fans)."""

  # Regular expressions used by thermal component.
  GET_FAN_SPEED_RE = re.compile(r'Fan (\d+) RPM: (\d+)')
  TEMPERATURE_RE = re.compile(r'^(\d+): (\d+)$', re.MULTILINE)
  TEMPERATURE_INFO_RE = re.compile(r'^(\d+): \d+ (.+)$', re.MULTILINE)

  AUTO = 'auto'
  """Constant representing automatic fan speed."""

  def __init__(self, dut):
    super(Thermal, self).__init__(dut)
    self._temperature_sensor_names = None
    self._main_temperature_index = None

  def GetTemperatures(self):
    """Gets a list of temperatures for various sensors.

    Returns:
      A list of int indicating the temperatures in Celsius.
      For those sensors which don't have readings, fill None instead.
    """
    try:
      ectool_output = self._dut.CallOutput(['ectool', 'temps', 'all'])
      temps = []
      for match in self.TEMPERATURE_RE.finditer(ectool_output):
        sensor = int(match.group(1))
        while len(temps) < sensor + 1:
          temps.append(None)
        # Convert Kelvin to Celsius and add
        temps[sensor] = int(match.group(2)) - 273 if match.group(2) else None
      return temps
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to get temperatures: %s' % e)

  def GetMainTemperatureIndex(self):
    """Gets the main index in temperatures list that should be logged.

    This is typically the CPU temperature.

    Returns:
      An int indicating the main temperature index.
    """
    if self._main_temperature_index is not None:
      return self._main_temperature_index
    try:
      names = self.GetTemperatureSensorNames()
      try:
        self._main_temperature_index = names.index('PECI')
        return self._main_temperature_index
      except ValueError:
        raise self.Error('The expected index of PECI cannot be found')
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to get main temperature index: %s' % e)

  def GetFanRPM(self, fan_id=None):
    """Gets the fan RPM.

    Args:
      fan_id: The id of the fan.

    Returns:
      A list of int indicating the RPM of each fan.
    """
    try:
      ectool_output = self._dut.CallOutput(
          ['ectool', 'pwmgetfanrpm'] + (['%d' % fan_id] if fan_id is not None
                                        else []))
      return [int(rpm[1])
              for rpm in self.GET_FAN_SPEED_RE.findall(ectool_output)]
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to get fan speed: %s' % e)

  def GetTemperatureSensorNames(self):
    """Gets a list of names for temperature sensors.

    Returns:
      A list of str containing the names of all temperature sensors.
      The order must be the same as the returned list from GetTemperatures().
    """
    if self._temperature_sensor_names is not None:
      return list(self._temperature_sensor_names)
    try:
      names = []
      ectool_output = self._dut.CallOutput(['ectool', 'tempsinfo', 'all'])
      for match in self.TEMPERATURE_INFO_RE.finditer(ectool_output):
        sensor = int(match.group(1))
        while len(names) < sensor + 1:
          names.append(None)
        names[sensor] = match.group(2)
      self._temperature_sensor_names = names
      return list(names)
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to get temperature sensor names: %s' % e)

  def SetFanRPM(self, rpm, fan_id=None):
    """Sets the target fan RPM.

    Args:
      rpm: Target fan RPM, or Thermal.AUTO for auto fan control.
      fan_id: The id of the fan.
    """
    try:
      # For system with multiple fans, ectool controls all the fans
      # simultaneously in one command.
      if rpm == self.AUTO:
        self._dut.CheckCall((['ectool', 'autofanctrl'] +
                             (['%d' % fan_id] if fan_id is not None else [])))
      else:
        self._dut.CheckCall((['ectool', 'pwmsetfanrpm'] +
                             (['%d' % fan_id] if fan_id is not None else []) +
                             ['%d' % rpm]))
    except Exception as e:  # pylint: disable=W0703
      if rpm == self.AUTO:
        raise self.Error('Unable to set auto fan control: %s' % e)
      else:
        raise self.Error('Unable to set fan speed to %d RPM: %s' % (rpm, e))



def main():
  """Test for local execution."""
  pass

if __name__ == '__main__':
  main()
