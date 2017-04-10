#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System thermal module.

This module reports readings from system thermal sensors and power usage.
"""

from __future__ import print_function

import logging
import re
import struct
import time

import factory_common  # pylint: disable=W0611
from cros.factory.device import component
from cros.factory.utils.type_utils import Enum


# Currently SensorSource is only used by thermal sensors. We may move it to
# other places if we see more modules having similar request, for example IIO
# sensors.
class SensorSource(component.DeviceComponent):
  """Provides minimal functions for reading sensor input.

  Attributes:
    _dut: A `cros.factory.device.board.DeviceBoard` instance.
    _sensors: A dictionary for cached sensor info (from `_Probe`).
  """

  def __init__(self, dut):
    """Constructor."""
    super(SensorSource, self).__init__(dut)
    self._sensors = None

  def _Probe(self):
    """Probes sensors available to the source provider.

    Derived source provider should override this function to probe and collect
    sensor information, and must make sure each sensor name is unique.

    Returns:
      A dictionary {name: info} that name is the name of sensor and info
      contains the information to how to read value from this sensor, for
      example system node path.
    """
    raise NotImplementedError

  def _ConvertRawValue(self, value):
    """Converts a raw value to meaningful values.

    Args:
      value: Raw value (string) fetched from sensor.

    Returns:
      A converted value.
    """
    raise NotImplementedError

  def GetMainSensorName(self):
    """Gets the name of main sensor.

    Returns:
      A string as sensor name for `GetValue` to use, or None if 'main' sensor is
      not applicable on current system.
    """
    return None

  def GetSensors(self):
    """Gets a (cached) dict of available sensors.

    Returns:
      A dictionary as {name: info}, see `_Probe` for details.
    """
    if self._sensors is not None:
      return self._sensors

    self._sensors = {}
    try:
      self._sensors.update(self._Probe())
    except Exception:
      logging.debug('Sensor source <%s> failed to probe sensors.',
                    self.__class__.__name__)
    return self._sensors

  def GetValue(self, sensor):
    """Gets current value from specified sensor.

    Args:
      sensor: A string of name (should be in the list of `GetSensors`).

    Returns:
      A processed value from sensor.
    """
    return self._ConvertRawValue(self._dut.ReadFile(self.GetSensors()[sensor]))

  def GetAllValues(self):
    """Gets all available sensor values.

    Returns:
      A dictionary {name: value} that is the name and value from sensor.
    """
    return dict([(name, self.GetValue(name)) for name in self.GetSensors()])


class ThermalSensorSource(SensorSource):
  """A special sensor source that returns thermal in Celsius."""

  def _Probe(self):
    """Probes thermal sensors."""
    raise NotImplementedError

  def _ConvertRawValue(self, value):
    """Converts raw value into number in Celsius."""
    raise NotImplementedError


class CoreTempSensors(ThermalSensorSource):
  """A thermal sensor source based on CoreTemp.

  CoreTemp is available on Intel CPUs, using Linux 'coretemp' driver
  (https://www.kernel.org/doc/Documentation/hwmon/coretemp).
  """

  def _Probe(self):
    """Probes coretemp sensors."""
    return dict(
        (self._dut.path.basename(self._dut.path.dirname(path)) + ' ' +
         self._dut.ReadFile(path.rsplit('_')[0] + '_label').strip(), path)
        for path in self._dut.Glob(
            '/sys/devices/platform/coretemp.*/temp*_input'))

  def _ConvertRawValue(self, value):
    """Converts coretemp raw values (milli-Celsius) into Celsius."""
    return int(value.strip()) / 1000

  def GetMainSensorName(self):
    """Returns the sensor name of main (first package) coretemp node."""
    for name, path in self.GetSensors().iteritems():
      # coretemp.0/temp1 is always the package of first CPU.
      if path == '/sys/devices/platform/coretemp.0/temp1_input':
        return name
    return None


class ThermalZoneSensors(ThermalSensorSource):
  """A thermal sensor source based on Linux Thermal Zone.

  Linux Thermal Zone is a general way of reading system thermal on most systems
  ( https://www.kernel.org/doc/Documentation/thermal/sysfs-api.txt).
  """

  def _Probe(self):
    """Probes thermal zone nodes from sysfs."""
    return dict(
        (self._dut.path.basename(node) + ' ' +
         self._dut.ReadFile(self._dut.path.join(node, 'type')).strip(),
         self._dut.path.join(node, 'temp'))
        for node in self._dut.Glob('/sys/class/thermal/thermal_zone*'))

  def _ConvertRawValue(self, value):
    """Converts thermal zone raw values (milli-Celsius) to Celsius."""
    return int(value.strip()) / 1000

  def GetMainSensorName(self):
    """Returns the main thermal zone (zone0) name."""
    for name, path in self.GetSensors().iteritems():
      if path == '/sys/class/thermal/thermal_zone0/temp':
        return name
    return None


class ECToolTemperatureSensors(ThermalSensorSource):
  """A thermal sensor source based on ChromeOS ECTool.

  ChromeOS ECTool allows reading thermals using 'temps' and 'tempsinfo'
  commands. These sensors are usually for peripherals like battery, charger, or
  other chipsets.
  """

  ECTOOL_TEMPSINFO_ALL_RE = re.compile(r'^(\d+): \d+ (.+)$', re.MULTILINE)
  """ectool 'tempsinfo all' output format: <id: type name>"""

  ECTOOL_TEMPS_ALL_RE = re.compile(r'^(\d+): (\d+)$', re.MULTILINE)
  """ectool 'temps all' output format: <id: value>"""

  def _Probe(self):
    """Probes ectool sensors by "tempsinfo all" command."""
    return dict(('ectool ' + name, sensor_id) for sensor_id, name in
                self.ECTOOL_TEMPSINFO_ALL_RE.findall(
                    self._dut.CallOutput('ectool tempsinfo all')))

  def _ConvertRawValue(self, value):
    """Converts ectool temperatures from Kelvin to Celsius."""
    return int(value.strip()) - 273 if value else None

  def GetValue(self, sensor):
    """Gets one single value with "temps" command."""
    sensor_id = self.GetSensors()[sensor]
    # 'ectool temps' prints a message like Reading 'temperature...(\d+)'
    return self._ConvertRawValue(
        self._dut.CallOutput('ectool temps %s' % sensor_id).rpartition('.')[2])

  def GetAllValues(self):
    """Returns all ectool temps values.

    ectool has a quick command 'temps all' that is faster then iterating all
    sensor with GetValue, so we want to implement GetAllValues explicitly.
    """
    raw_values = dict([
        (sensor_id, value) for sensor_id, value in
        self.ECTOOL_TEMPS_ALL_RE.findall(
            self._dut.CallOutput('ectool temps all'))])

    # Remap ID to cached names.
    return dict((name, self._ConvertRawValue(raw_values.get(sensor_id)))
                for name, sensor_id in self.GetSensors().iteritems())


class Thermal(component.DeviceComponent):
  """System module for thermal info (temperature sensors, power usage).

  Attributes:
    _sensors: A cached dictionary {sensor_name: source} by `_SetupSensors`.
    _main_sensor: A string indicating system main sensor or None.
    _sources: A cached list of sensor sources.
    _sensor_list: An ordered list of sensor names.
  """

  AUTO = 'auto'
  """Deprecated by fan.FanControl.AUTO."""

  MSR_PKG_ENERGY_STATUS = 0x611
  """MSR location for energy status. See <http://lwn.net/Articles/444887/>."""

  ENERGY_UNIT_FACTOR = 1.53e-5
  """Factor to use to convert energy readings to Joules."""

  def __init__(self, dut):
    """Constructor."""
    super(Thermal, self).__init__(dut)
    self._sensors = None
    self._main_sensor = None
    self._sources = []
    # TODO(hungte): sensors_list is a special list for GetTemperatures
    # to work. We may drop it in future.
    self._sensors_list = None

  def _AddThermalSensorSource(self, source):
    """Adds a thermal sensor source into registered sensors.

    Also updates current main sensor if it's not configured yet.

    Args:
      source: An instance of `ThermalSensorSource`.
    """
    sensors = dict((name, source) for name in source.GetSensors())
    if not sensors:
      return
    self._sensors.update(sensors)
    self._sources.append(source)
    if not self._main_sensor:
      self._main_sensor = source.GetMainSensorName()

  def _SetupSensors(self):
    """Configures available sensors.

    Derived implementations can override this to modify the priority and type of
    sensors.
    """
    self._sensors = {}
    self._main_sensor = None
    self._sources = []

    # CoreTemp should be considered as the better alternative than ThermalZone.
    self._AddThermalSensorSource(CoreTempSensors(self._dut))
    if not self._main_sensor:
      self._AddThermalSensorSource(ThermalZoneSensors(self._dut))
    # ECTool provides additional sensors.
    self._AddThermalSensorSource(ECToolTemperatureSensors(self._dut))

  def _GetSensors(self):
    """Gets (cached) available sensors."""
    if self._sensors is not None:
      return self._sensors
    try:
      self._SetupSensors()
    except Exception:
      logging.debug('%s: Failed setting up sensors.', self.__class__.__name__)
    assert len(set(self._sensors.values())) == len(self._sources), (
        'Sensor source cache does not match logged sensors')
    self._sensors_list = self._sensors.keys()
    return self._sensors

  def GetMainSensorName(self):
    """Returns the name of main sensor.

    This is typically the CPU temperature sensor.

    Returns:
      A string as sensor name, or None if not available.
    """
    # Call _GetSensors explicitly to make sure sensors setup is done.
    self._GetSensors()
    return self._main_sensor

  def GetAllSensorNames(self):
    """Returns names of all available sensors."""
    return self._GetSensors().keys()

  def GetTemperature(self, sensor_name=None):
    """Gets current temperature of specified sensor.

    Args:
      sensor_name: The name of sensor to read. Default to main sensor.

    Returns:
      A number indicating the temperature in Celsius.
    """
    if sensor_name is None:
      sensor_name = self.GetMainSensorName()
    return self._GetSensors()[sensor_name].GetValue(sensor_name)

  def GetAllTemperatures(self):
    """Gets temperature from all sensors.

    Returns:
      A mapping from sensor name to temperature in Celsius.
    """
    self._GetSensors()
    values = {}
    for source in self._sources:
      values.update(source.GetAllValues())
    return values

  def GetMainTemperature(self):
    """Deprecated. Gets the temperature of main sensor.

    This is typically the CPU temperature.

    Returns:
      A number indicating the temperature in Celsius.
    """
    return self.GetTemperature()

  def GetTemperatures(self):
    """Deprecated. Gets a list of temperatures for various sensors.

    The list is using same order as `GetTemperatureSensorNames`

    Returns:
      A list of int indicating the temperatures in Celsius.
      For those sensors which don't have readings, fill None instead.
    """
    values = self.GetAllTemperatures()
    return [values[name] for name in self.GetTemperatureSensorNames()]

  def GetMainTemperatureIndex(self):
    """Deprecated. Gets the index of main sensor in `GetTemperatures`.

    The list is using same order as `GetTemperatureSensorNames`

    Returns:
      An int indicating the main temperature index.
    """
    return self.GetTemperatureSensorNames().index(
        self.GetMainSensorName())

  def GetTemperatureSensorNames(self):
    """Deprecated. Gets a list of names for temperature sensors.

    The list is in fixed order.

    Returns:
      A list of str containing the names of all temperature sensors.
      The order must be the same as the returned list from GetTemperatures().
    """
    # Call _GetSensors explicitly to make sure sensors setup is done.
    self._GetSensors()
    return self._sensors_list

  def GetPowerUsage(self, last=None, sensor_id=None):
    """Gets current power usage.

    Args:
      last: The last snapshot read.
      sensor_id: Platform specific ID to specify the power sensor.

    Returns:
      A dict contains following fields:
        'time': Current timestamp.
        'energy': Cumulative energy use in Joule, optional.
        'power': Average power use in Watt, optional.
    """
    del sensor_id  # Not required for default implementation.
    pkg_energy_status = self._dut.ReadFile('/dev/cpu/0/msr', count=8,
                                           skip=self.MSR_PKG_ENERGY_STATUS)
    pkg_energy_j = (struct.unpack('<Q', pkg_energy_status)[0] *
                    self.ENERGY_UNIT_FACTOR)

    current_time = time.time()
    if last is not None:
      time_delta = current_time - last['time']
      pkg_power_w = (pkg_energy_j - last['energy']) / time_delta
    else:
      pkg_power_w = None

    return dict(time=current_time, energy=pkg_energy_j, power=pkg_power_w)

  def GetFanRPM(self, fan_id=None):
    """This function should be deprecated by `fan.GetFanRPM`."""
    return self._dut.fan.GetFanRPM(fan_id)

  def SetFanRPM(self, rpm, fan_id=None):
    """This function should be deprecated by `fan.SetFanRPM`."""
    return self._dut.fan.SetFanRPM(rpm, fan_id)


class ECToolThermal(Thermal):
  """Backward compatible name."""
  pass


# TODO(hungte) Part of SysFSThermal can be replaced by the ThermalZoneSensors
# but this is more generic and needs further testing on Android before we can
# eliminate it.
class SysFSThermal(Thermal):
  """System module for thermal sensors (temperature sensors, power usage).

  Implementation for systems which able to control thermal with sysfs api.
  """

  _SYSFS_THERMAL_PATH = '/sys/class/thermal/'

  Unit = Enum(['MILLI_CELSIUS', 'CELSIUS'])

  def __init__(self, dut, main_temperature_sensor_name='tsens_tz_sensor0',
               unit=Unit.MILLI_CELSIUS):
    """Constructor.

    Args:
      main_temperature_sensor_name: The name of temperature sensor used in
          GetMainTemperatureIndex(). For example: 'tsens_tz_sensor0' or 'cpu'.
      unit: The unit of the temperature reported in sysfs, in type
          SysFSThermal.Unit.
    """
    super(SysFSThermal, self).__init__(dut)
    self._thermal_zones = None
    self._temperature_sensor_names = None
    self._main_temperature_sensor_name = main_temperature_sensor_name
    self._unit = unit

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

  def GetMainTemperature(self):
    # TODO(hungte) Improve this by reading only required value.
    return self.GetTemperatures()[self.GetMainTemperatureIndex()]

  def GetTemperatures(self):
    """See Thermal.GetTemperatures."""
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
    """See Thermal.GetMainTemperatureIndex."""
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
    """See Thermal.GetTemperatureSensorNames."""
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

  def GetPowerUsage(self, last=None, sensor_id=''):
    """See Thermal.GetPowerUsage."""
    sensor = self._dut.hwmon.FindOneDevice('label', sensor_id)
    power = int(sensor.GetAttribute('power1_input')) / 1000 # convert mW to W
    return dict(time=time.time(), energy=None, power=power)


def main():
  """Test for local execution."""
  pass


if __name__ == '__main__':
  main()
