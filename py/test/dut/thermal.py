#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System thermal provider.

This module provides reading and setting system thermal sensors and controllers.
"""

from __future__ import print_function

import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.utils.type_utils import Enum


class Thermal(component.DUTComponent):
  """System module for thermal control (temperature sensors, fans)."""

  AUTO = 'auto'
  """Constant representing automatic fan speed."""

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
      An int indicating the main temperature index.
    """
    raise NotImplementedError

  def GetFanRPM(self, fan_id=None):
    """Gets the fan RPM.

    Args:
      fan_id: The id of the fan.

    Returns:
      A list of int indicating the RPM of each fan.
    """
    raise NotImplementedError

  def GetTemperatureSensorNames(self):
    """Gets a list of names for temperature sensors.

    Returns:
      A list of str containing the names of all temperature sensors.
      The order must be the same as the returned list from GetTemperatures().
    """
    raise NotImplementedError

  def SetFanRPM(self, rpm, fan_id=None):
    """Sets the target fan RPM.

    Args:
      rpm: Target fan RPM, or ECToolThermal.AUTO for auto fan control.
      fan_id: The id of the fan.
    """
    raise NotImplementedError


class ECToolThermal(Thermal):
  """System module for thermal control (temperature sensors, fans).

  Implementation for systems with 'ectool' and able to control thermal with EC.
  """

  # Regular expressions used by thermal component.
  GET_FAN_SPEED_RE = re.compile(r'Fan (\d+) RPM: (\d+)')
  TEMPERATURE_RE = re.compile(r'^(\d+): (\d+)$', re.MULTILINE)
  TEMPERATURE_INFO_RE = re.compile(r'^(\d+): \d+ (.+)$', re.MULTILINE)

  def __init__(self, dut):
    super(ECToolThermal, self).__init__(dut)
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
      rpm: Target fan RPM, or ECToolThermal.AUTO for auto fan control.
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


class SysFSThermal(Thermal):
  """System module for thermal control (temperature sensors, fans).

  Implementation for systems which able to control thermal with sysfs api.
  """

  _SYSFS_THERMAL_PATH = '/sys/class/thermal/'

  Unit = Enum(['MILLI_CELSIUS', 'CELSIUS'])

  def __init__(self, dut, main_temperature_sensor_name='tsens_tz_sensor0',
               unit=Unit.MILLI_CELSIUS, fans_info=None):
    """Constructor.

    Args:
      main_temperature_sensor_name: The name of temperature sensor used in
          GetMainTemperatureIndex(). For example: 'tsens_tz_sensor0' or 'cpu'.
      unit: The unit of the temperature reported in sysfs, in type
          SysFSThermal.Unit.
      fans_info: A sequence of dicts. Each dict contains information of a fan:
      - "fan_id": The id used in SetFanRPM/GetFanRPM.
      - "path": The path containing files for fan operations.
      - "control_mode_filename": The file to switch auto/manual fan control
            mode. default is "pwm1_enable".
      - "get_speed_filename": The file to get fan speed information.
            default is "fan1_input".
      - "get_speed_map": A function (str -> int) that translates the content of
            "get_speed_filename" file to RPM. default is int.
      - "set_speed_filename": The file to set fan speed. default is "pwm1".
      - "set_speed_map": A function (int -> str) that produces corresponding
            content for "set_speed_filename" file with a given RPM. default is
            str.
    """
    super(SysFSThermal, self).__init__(dut)
    self._thermal_zones = None
    self._temperature_sensor_names = None
    self._main_temperature_sensor_name = main_temperature_sensor_name
    self._unit = unit
    self._fans = []
    if fans_info is not None:
      for fan_info in fans_info:
        complete_info = fan_info.copy()
        assert 'fan_id' in complete_info, "'fan_id' is missing in fans_info"
        assert 'path' in complete_info, "'path' is missing in fans_info"
        complete_info.setdefault('control_mode_filename', 'pwm1_enable')
        complete_info.setdefault('get_speed_filename', 'fan1_input')
        complete_info.setdefault('get_speed_map', int)
        complete_info.setdefault('set_speed_filename', 'pwm1')
        complete_info.setdefault('set_speed_map', str)
        self._fans.append(complete_info)

  def _ConvertTemperatureToCelsius(self, value):
    """
    Args:
      value: Temperature value in self._unit.

    Returns:
      The value in degree Celsius.
    """
    conversion_map = {
        self.Unit.MILLI_CELSIUS: lambda x: x / 1000,
        self.Unit.CELSIUS: lambda x: x
    }
    return conversion_map[self._unit](value)

  def _GetThermalZones(self):
    """Gets a list of thermal zones.

    Returns:
      A list of absolute path of thermal zones.
    """
    if self._thermal_zones is None:
      self._thermal_zones = self._dut.Glob(self._dut.path.join(
          self._SYSFS_THERMAL_PATH, 'thermal_zone*'))
    return self._thermal_zones

  def GetTemperatures(self):
    """See ECToolThermal.GetTemperatures."""
    try:
      temperatures = []
      for path in self._GetThermalZones():
        try:
          temp = self._dut.ReadFile(self._dut.path.join(path, 'temp'))
          # Convert temperature values to Celsius for output.
          temperatures.append(self._ConvertTemperatureToCelsius(int(temp)))
        except component.CalledProcessError:
          temperatures.append(None)
      logging.debug("GetTemperatures: %s", temperatures)
      return temperatures
    except component.CalledProcessError as e:
      raise self.Error('Unable to get temperatures: %s' % e)

  def GetMainTemperatureIndex(self):
    """See ECToolThermal.GetMainTemperatureIndex."""
    try:
      names = self.GetTemperatureSensorNames()
      try:
        return names.index(self._main_temperature_sensor_name)
      except ValueError:
        raise self.Error('The expected index of %s cannot be found',
                         self._main_temperature_sensor_name)
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to get main temperature index: %s' % e)

  def GetTemperatureSensorNames(self):
    """See ECToolThermal.GetTemperatureSensorNames."""
    if self._temperature_sensor_names is None:
      try:
        self._temperature_sensor_names = []
        for path in self._GetThermalZones():
          name = self._dut.ReadFile(self._dut.path.join(path, 'type'))
          self._temperature_sensor_names.append(name.strip())
        logging.debug("GetTemperatureSensorNames: %s",
                      self._temperature_sensor_names)
      except component.CalledProcessError as e:
        raise self.Error('Unable to get temperature sensor names: %s' % e)
    return self._temperature_sensor_names

  def GetFanRPM(self, fan_id=None):
    """See ECToolThermal.GetFanRPM."""
    try:
      ret = []
      for info in self._fans:
        if fan_id is None or info['fan_id'] == fan_id:
          buf = self._dut.ReadFile(self._dut.path.join(
              info['path'], info['get_speed_filename']))
          ret.append(info['get_speed_map'](buf))
      return ret
    except Exception as e:  # pylint: disable=W0703
      raise self.Error('Unable to get fan speed: %s' % e)

  def SetFanRPM(self, rpm, fan_id=None):
    """See ECToolThermal.SetFanRPM."""
    try:
      for info in self._fans:
        if fan_id is None or info['fan_id'] == fan_id:
          if rpm == self.AUTO:
            self._dut.WriteFile(self._dut.path.join(
                info['path'], info['control_mode_filename']), '2')
          else:
            self._dut.WriteFile(self._dut.path.join(
                info['path'], info['control_mode_filename']), '1')
            buf = info['set_speed_map'](rpm)
            self._dut.WriteFile(self._dut.path.join(
                info['path'], info['set_speed_filename']), buf)
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
