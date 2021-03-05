# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""System thermal module.

This module reports readings from system thermal sensors and power usage.
"""

import logging
import re
import struct
import time

from cros.factory.device import device_types


# Currently SensorSource is only used by thermal sensors. We may move it to
# other places if we see more modules having similar request, for example IIO
# sensors.
class SensorSource(device_types.DeviceComponent):
  """Provides minimal functions for reading sensor input.

  Attributes:
    _device: A `cros.factory.device.device_types.DeviceInterface` instance.
    _sensors: A dictionary for cached sensor info (from `_Probe`).
  """

  def __init__(self, device):
    """Constructor."""
    super(SensorSource, self).__init__(device)
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
    sensor_path = self.GetSensors()[sensor]
    try:
      return self._ConvertRawValue(self._device.ReadFile(sensor_path))
    except IOError:
      logging.warning("Failed to get temperature from %s", sensor_path)
      return -1

  def GetAllValues(self):
    """Gets all available sensor values.

    Returns:
      A dictionary {name: value} that is the name and value from sensor.
    """
    return {name: self.GetValue(name) for name in self.GetSensors()}


class ThermalSensorSource(SensorSource):
  """A special sensor source that returns thermal in Celsius."""

  def _Probe(self):
    """Probes thermal sensors."""
    raise NotImplementedError

  def _ConvertRawValue(self, value):
    """Converts raw value into number in Celsius."""
    raise NotImplementedError

  def GetCriticalValue(self, sensor):
    """Gets the critical temperature of the corrosponding component.

    Returns:
      A number indicates the critical temperature in Celsius.
    """
    raise NotImplementedError


class CoreTempSensors(ThermalSensorSource):
  """A thermal sensor source based on CoreTemp.

  CoreTemp is available on Intel CPUs, using Linux 'coretemp' driver
  (https://www.kernel.org/doc/Documentation/hwmon/coretemp).
  """

  def _Probe(self):
    """Probes coretemp sensors."""
    def _GetSensorName(coretemp_path, input_path):
      label_path = input_path.rpartition('_')[0] + '_label'
      return (self._device.path.basename(coretemp_path) + ' ' +
              self._device.ReadFile(label_path).strip())

    result = {}
    for coretemp_base in self._device.Glob('/sys/devices/platform/coretemp.*'):
      # For newer version of linux kernel, CoreTemp is integrated with hwmon.
      for median_dirs in ['', 'hwmon/hwmon*']:
        curr_result = dict(
            (_GetSensorName(coretemp_base, input_path), input_path)
            for input_path in self._device.Glob(self._device.path.join(
                coretemp_base, median_dirs, 'temp*_input')))
        if curr_result:
          result.update(curr_result)
          break
    return result

  def _ConvertRawValue(self, value):
    """Converts coretemp raw values (milli-Celsius) into Celsius."""
    return int(value.strip()) // 1000

  def GetMainSensorName(self):
    """Returns the sensor name of main (first package) coretemp node."""
    for name, path in self.GetSensors().items():
      if 'coretemp.0' in path and path.endswith('temp1_input'):
        return name
    return None

  def GetCriticalValue(self, sensor):
    path = self.GetSensors()[sensor].rpartition('_')[0] + '_crit'
    return self._ConvertRawValue(self._device.ReadFile(path))


class ThermalZoneSensors(ThermalSensorSource):
  """A thermal sensor source based on Linux Thermal Zone.

  Linux Thermal Zone is a general way of reading system thermal on most systems
  ( https://www.kernel.org/doc/Documentation/thermal/sysfs-api.txt).
  """

  def _Probe(self):
    """Probes thermal zone nodes from sysfs."""
    # TODO(hungte) Some systems may have sensors disabled (mode='disabled') and
    # reading 'value' form them will fail. We may need to support that in future
    # if needed.
    return dict(
        (self._device.path.basename(node) + ' ' +
         self._device.ReadFile(self._device.path.join(node, 'type')).strip(),
         self._device.path.join(node, 'temp'))
        for node in self._device.Glob('/sys/class/thermal/thermal_zone*'))

  def _ConvertRawValue(self, value):
    """Converts thermal zone raw values (milli-Celsius) to Celsius."""
    return int(value.strip()) // 1000

  def GetMainSensorName(self):
    """Returns the main thermal zone (zone0) name."""
    for name, path in self.GetSensors().items():
      if path == '/sys/class/thermal/thermal_zone0/temp':
        return name
    return None

  def GetCriticalValue(self, sensor):
    raise NotImplementedError


class ECToolTemperatureSensors(ThermalSensorSource):
  """A thermal sensor source based on ChromeOS ECTool.

  ChromeOS ECTool allows reading thermals using 'temps' and 'tempsinfo'
  commands. These sensors are usually for peripherals like battery, charger, or
  other chipsets.
  """

  ECTOOL_TEMPSINFO_ALL_RE = re.compile(r'^(\d+): \d+ (.+)$', re.MULTILINE)
  """ectool 'tempsinfo all' output format: <id: type name>"""

  ECTOOL_TEMPS_ALL_RE = re.compile(r'^(\d+): (\d+)(?: K)?$', re.MULTILINE)
  """ectool 'temps all' output format: <id: value>"""

  ECTOOL_TEMPS_SENSORID_RE = re.compile(r'(\d+)(?: K)?$')
  """ectool 'temps sensor_id' output format: <Reading temperature...305 K>"""

  def _Probe(self):
    """Probes ectool sensors by "tempsinfo all" command."""
    return {'ectool ' + name: sensor_id for sensor_id, name in
            self.ECTOOL_TEMPSINFO_ALL_RE.findall(
                self._device.CallOutput('ectool tempsinfo all'))}

  def _ConvertRawValue(self, value):
    """Converts ectool temperatures from Kelvin to Celsius."""
    return int(value.strip()) - 273 if value else None

  def GetValue(self, sensor):
    """Gets one single value with "temps" command."""
    sensor_id = self.GetSensors()[sensor]
    # 'ectool temps' prints a message like Reading 'temperature...(\d+)'
    return self._ConvertRawValue(
        self.ECTOOL_TEMPS_SENSORID_RE.findall(
            self._device.CallOutput('ectool temps %s' % sensor_id))[0])

  def GetAllValues(self):
    """Returns all ectool temps values.

    ectool has a quick command 'temps all' that is faster then iterating all
    sensor with GetValue, so we want to implement GetAllValues explicitly.
    """
    raw_values = dict(self.ECTOOL_TEMPS_ALL_RE.findall(
        self._device.CallOutput('ectool temps all')))

    # Remap ID to cached names.
    return {name: self._ConvertRawValue(raw_values.get(sensor_id))
            for name, sensor_id in self.GetSensors().items()}

  def GetCriticalValue(self, sensor):
    raise NotImplementedError


class Thermal(device_types.DeviceComponent):
  """System module for thermal info (temperature sensors, power usage).

  Attributes:
    _sensors: A cached dictionary {sensor_name: source} by `_SetupSensors`.
    _main_sensor: A string indicating system main sensor or None.
    _sources: A cached list of sensor sources.
  """

  MSR_PKG_ENERGY_STATUS = 0x611
  """MSR location for energy status. See <http://lwn.net/Articles/444887/>."""

  ENERGY_UNIT_FACTOR = 1.53e-5
  """Factor to use to convert energy readings to Joules."""

  SOURCE_CLASSES = [
      # ECToolTemperatureSensors doesn't have main sensor name, so it is safe to
      # add it in the beginning of the list.
      ECToolTemperatureSensors,
      # CoreTempSensors is preferred over ThermalZoneSensors.  It returns main
      # sensor if found. If not found, it normally means that CoreTempSensors is
      # not supported on this device, and we will fallback to next
      # implementation: ThermalZoneSensors.
      CoreTempSensors,
      # ThermalZoneSensors is the fallback option, it should be available on
      # most Linux devices, if sensors are not disabled.
      ThermalZoneSensors,
  ]
  """A list of ThermalSensorSource to load in _SetupSensors function.

  Each source will be created in order, and their sensors will be added to
  self._sensors, until we find the first source that has a main sensor name.
  """

  def __init__(self, dut):
    """Constructor."""
    super(Thermal, self).__init__(dut)
    self._sensors = None
    self._main_sensor = None
    self._sources = []

  def _AddThermalSensorSource(self, source):
    """Adds a thermal sensor source into registered sensors.

    Also updates current main sensor if it's not configured yet.

    Args:
      source: An instance of `ThermalSensorSource`.
    """
    sensors = {name: source for name in source.GetSensors()}
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

    for source_class in self.SOURCE_CLASSES:
      assert issubclass(source_class, ThermalSensorSource)
      source = source_class(self._device)
      self._AddThermalSensorSource(source)
      if self._main_sensor:
        break

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
    return list(self._GetSensors())

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

  def GetCriticalTemperature(self, sensor_name=None):
    """Gets critical temperature bound of the specified sensor.

    Args:
      sensor_name: The name of sensor to read. Default to main sensor.

    Returns:
      A number indicating the critical temperature.
    """
    if sensor_name is None:
      sensor_name = self.GetMainSensorName()
    return self._GetSensors()[sensor_name].GetCriticalValue(sensor_name)

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
    pkg_energy_status = self._device.ReadSpecialFile(
        '/dev/cpu/0/msr', count=8, skip=self.MSR_PKG_ENERGY_STATUS,
        encoding=None)
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
    return self._device.fan.GetFanRPM(fan_id)

  def SetFanRPM(self, rpm, fan_id=None):
    """This function should be deprecated by `fan.SetFanRPM`."""
    return self._device.fan.SetFanRPM(rpm, fan_id)
