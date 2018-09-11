# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import math

import factory_common  # pylint: disable=unused-import
from cros.factory.device import sensor_utils
from cros.factory.device import types


_RADIAN_TO_DEGREE = 180 / math.pi


class GyroscopeController(sensor_utils.BasicSensorController):
  """Utility class for gyroscope.

  According to
  https://docs.google.com/document/d/1-ZLlS8oJNkFUA0wCNsPukJOZjwVIWOvs9404ihdEm6M/edit#heading=h.2bak5m7fwmoz
  the unit of (_raw data * scale) is rad/s and the unit of _calibbias is dps.

  Attributes:
    name: the name of the gyroscope, e.g., 'cros-ec-gyro', or None.
      This will be used to lookup a matched name in
      /sys/bus/iio/devices/iio:deviceX/name to get
      the corresponding iio:deviceX.
      At least one of name or location must present.

    location: the location of the accelerometer, e.g., 'base' or 'lid', or
      None. This will be used to lookup a matched location in
      /sys/bus/iio/devices/iio:deviceX/location to get
      the corresponding iio:deviceX.
      At least one of name or location must present.
  """

  def __init__(self, board, name, location):
    super(GyroscopeController, self).__init__(
        board, name, location, ['in_anglvel_x', 'in_anglvel_y', 'in_anglvel_z'],
        scale=True)
    self.location = location

  def CleanUpCalibrationValues(self):
    """Clean up calibration values.

    The sysfs trigger only captures calibrated input values, so we reset
    the calibration to allow reading raw data from a trigger.
    """
    for signal_name in self.signal_names:
      self._SetSysfsValue('%s_calibbias' % signal_name, '0')

  def CalculateCalibrationBias(self, data):
    """Calculating calibration data."""
    calib_bias = {}
    for signal_name in data:
      ideal_value = 0
      current_calib_bias = (
          int(self._GetSysfsValue('%s_calibbias' % signal_name))
          / _RADIAN_TO_DEGREE / 1024)
      # Calculate the difference between the ideal value and actual value
      # then store it into _calibbias.  In release image, the raw data will
      # be adjusted by _calibbias to generate the 'post-calibrated' values.
      calib_bias[signal_name + '_' + self.location + '_calibbias'] = (
          ideal_value - data[signal_name] + current_calib_bias)
    return calib_bias

  def UpdateCalibrationBias(self, calib_bias):
    """Update calibration bias to RO_VPD.

    Args:
      A dict of calibration bias in, rad/s.
      For example, {'in_anglvel_x_base_calibbias': 0.1,
                    'in_anglvel_y_base_calibbias': -0.2,
                    'in_anglvel_z_base_calibbias': 0.3}
    """
    logging.info('Calibration results: %s.', calib_bias)
    # The data is converted to 1/1024dps unit before writing.
    scaled = dict((k, str(int(v * 1024 * _RADIAN_TO_DEGREE)))
                  for k, v in calib_bias.viewitems())
    self._device.vpd.ro.Update(scaled)
    mapping = []
    for signal_name in self.signal_names:
      mapping.append(('%s_%s_calibbias' % (signal_name, self.location),
                      '%s_calibbias' % signal_name))
    for vpd_entry, sysfs_entry in mapping:
      self._SetSysfsValue(sysfs_entry, scaled[vpd_entry])


class Gyroscope(types.DeviceComponent):
  """Gyroscope component module."""

  def GetController(self, location='base'):
    """Gets a controller with specified arguments.

    See sensor_utils.BasicSensorController for more information.
    """
    return GyroscopeController(self._device, 'cros-ec-gyro', location)
