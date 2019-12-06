# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os

from cros.factory.device import device_types
from cros.factory.device import sensor_utils


IN_ILLUMINANCE_BIAS = "in_illuminance_calibbias"
IN_ILLUMINANCE_SCALE = "in_illuminance_calibscale"


class AmbientLightSensorException(Exception):
  pass


class AmbientLightSensorController(sensor_utils.BasicSensorController):

  def __init__(self, dut, name, location):
    """Constructor.

    Args:
      dut: The DUT instance.
      name: The name attribute of sensor.
      location: The location attribute of sensor.
    """
    super(AmbientLightSensorController, self).__init__(
        dut, name, location, [IN_ILLUMINANCE_BIAS, IN_ILLUMINANCE_SCALE])
    self.calib_signal_names = [IN_ILLUMINANCE_BIAS, IN_ILLUMINANCE_SCALE]
    self.location = location
    for input_entry in ['in_illuminance_input', 'in_illuminance_raw']:
      if self._device.Glob(self._device.path.join(self._iio_path, input_entry)):
        self.input_entry = input_entry
        self.signal_names.append(self.input_entry)
        break
    if not self.input_entry:
      raise AmbientLightSensorException('Does not find any input entry.')

  def _SetSysfsValue(self, filename, value, check_call=True, path=None):
    del check_call, path  # Unused.
    try:
      self._device.WriteSpecialFile(
          os.path.join(self._iio_path, filename), value)
    except Exception as e:
      raise AmbientLightSensorException(str(e))

  def _GetSysfsValue(self, filename, path=None):
    del path  # Unused.
    try:
      return self._device.ReadSpecialFile(os.path.join(
          self._iio_path, filename)).strip()
    except Exception as e:
      raise AmbientLightSensorException(str(e))

  def CleanUpCalibrationValues(self):
    """Cleans up calibration values."""
    self._SetSysfsValue(IN_ILLUMINANCE_BIAS, '0.0')
    self._SetSysfsValue(IN_ILLUMINANCE_SCALE, '1.0')

  def GetCalibrationValues(self):
    """Reads the calibration values from sysfs."""
    vals = {}
    for signal_name in self.calib_signal_names:
      vals[signal_name] = float(self._GetSysfsValue(signal_name))
    return vals

  def SetCalibrationValue(self, signal_name, value):
    """Sets the calibration values to sysfs."""
    if signal_name not in self.calib_signal_names:
      raise KeyError(signal_name)
    try:
      self._SetSysfsValue(signal_name, value)
    except Exception as e:
      raise AmbientLightSensorException(str(e))

  def SetCalibrationIntercept(self, value):
    """Sets the calibration bias to sysfs."""
    try:
      self._SetSysfsValue(IN_ILLUMINANCE_BIAS, str(value))
    except Exception as e:
      raise AmbientLightSensorException(str(e))

  def SetCalibrationSlope(self, value):
    """Sets the calibration scale to sysfs."""
    try:
      self._SetSysfsValue(IN_ILLUMINANCE_SCALE, str(value))
    except Exception as e:
      raise AmbientLightSensorException(str(e))

  def GetLuxValue(self):
    """Reads the LUX raw value from sysfs."""
    try:
      return int(self._GetSysfsValue(self.input_entry))
    except Exception as e:
      logging.exception('Failed to get illuminance value')
      raise AmbientLightSensorException(str(e))

  def ForceLightInit(self):
    """Froce als to apply the vpd value."""
    try:
      device_name = os.path.basename(self._iio_path)
      self._device.CheckCall('/lib/udev/light-init.sh',
                             stdin=device_name, stdout='illuminance')
    except Exception as e:
      logging.exception('Failed to invoke light-init.sh (%s, illuminance)',
                        device_name)
      raise AmbientLightSensorException(str(e))


class AmbientLightSensor(device_types.DeviceComponent):
  """AmbientLightSensor (ALS) component module."""

  def GetController(self, name='cros-ec-light', location='lid'):
    """Gets a controller with specified arguments.

    See AmbientLightSensorController for more information.
    """
    return AmbientLightSensorController(self._device, name, location)
