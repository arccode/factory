# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import time

from cros.factory.device import device_types
from cros.factory.device import sensor_utils
from cros.factory.utils import process_utils


_GRAVITY = 9.80665

class AccelerometerException(Exception):
  pass


class AccelerometerController(sensor_utils.BasicSensorController):
  """Utility class for the two accelerometers.

  Attributes:
    name: the name of the accelerometer, e.g., 'cros-ec-accel', or None.
      This will be used to lookup a matched name in
      /sys/bus/iio/devices/iio:deviceX/name to get
      the corresponding iio:deviceX.
      At least one of name or location must present.

    location: the location of the accelerometer, e.g., 'base' or 'lid', or
      None. This will be used to lookup a matched location in
      /sys/bus/iio/devices/iio:deviceX/location to get
      the corresponding iio:deviceX.
      At least one of name or location must present.

  Raises:
    Raises AccelerometerException if there is no accelerometer.
  """

  def __init__(self, board, name, location):
    """Cleans up previous calibration values and stores the scan order.

    We can get raw data from below sysfs:
      /sys/bus/iio/devices/iio:deviceX/in_accel_(x|y|z)_raw.

    However, there is no guarantee that the data will have been sampled
    at the same time. So we use `iioservice_simpleclient` to query the
    sensor data.
    """
    super(AccelerometerController, self).__init__(
        board, name, location, ['in_accel_x', 'in_accel_y', 'in_accel_z'],
        scale=True)
    self.location = location

  def CleanUpCalibrationValues(self):
    """Clean up calibration values.

    The sysfs trigger only captures calibrated input values, so we reset
    the calibration to allow reading raw data from a trigger.
    """
    for signal_name in self.signal_names:
      self._SetSysfsValue('%s_calibbias' % signal_name, '0')

  def GetData(self, capture_count: int = 1, sample_rate: float = None):
    """Returns average values of the sensor data.

    Use `iioservice_simpleclient` to capture the sensor data.

    Args:
      capture_count: how many records to read to compute the average.
      sample_rate: sample rate in Hz to read data from accelerometers. If it is
        None, set to the maximum frequency.

    Returns:
      A dict of the format {'signal_name': average value}
      The output data is in m/s^2.
      Ex, {'in_accel_x': 0,
           'in_accel_y': 0,
           'in_accel_z': 9.8}

    Raises:
      Raises AccelerometerException if there is no calibration
      value in VPD.
    """

    # Initializes the returned dict.
    ret = {signal_name: 0.0 for signal_name in self.signal_names}

    def ToChannelName(signal_name):
      """Transform the signal names (in_accel_(x|y|z)) to the channel names used
      in iioservice (accel_(x|y|z))."""

      return signal_name[3:] if signal_name.startswith('in_') else signal_name

    iioservice_channels = [
        ToChannelName(signal_name) for signal_name in self.signal_names
    ]

    # We only test `iioservice_simpleclient` with maximum frequency in
    # sensor_iioservice_hard.go. Use maximum frequency by default to make sure
    # that our tests are using tested commands.
    if sample_rate is None:
      frequencies = self.GetSamplingFrequencies()
      sample_rate = frequencies[1]

    iioservice_cmd = [
        'iioservice_simpleclient',
        '--channels=%s' % ' '.join(iioservice_channels),
        '--frequency=%f' % sample_rate,
        '--device_id=%d' % int(self._GetSysfsValue('dev').split(':')[1]),
        '--samples=1'
    ]
    logging.info('iioservice_simpleclient command: %r', iioservice_cmd)
    # Reads the captured data.
    data_captured = 0
    while data_captured < capture_count:
      time.sleep(1 / sample_rate)
      proc = process_utils.CheckCall(iioservice_cmd, read_stderr=True)
      for signal_name in self.signal_names:
        channel_name = ToChannelName(signal_name)
        match = re.search(r'(?<={}: )-?\d+'.format(channel_name),
                          proc.stderr_data)
        if not match:
          logging.error(
              'Failed to read channel "%s" from iioservice_simpleclient. '
              'stderr:\n%s', channel_name, proc.stderr_data)
          raise AccelerometerException
        ret[signal_name] += int(match[0])
        logging.info('(%d) Getting data on channel %s: %d', data_captured,
                     channel_name, int(match[0]))
      data_captured += 1
    # Calculates average value and convert to SI unit.
    for signal_name in ret:
      ret[signal_name] = (ret[signal_name] / capture_count * self.scale)
    logging.info('Average of %d data: %s', capture_count, ret)
    return ret

  @staticmethod
  def IsWithinOffsetRange(data, orientations, spec_offset):
    """Checks whether the value of sensor data is within the spec or not.

    It is used before calibration to filter out abnormal accelerometers.

    Args:
      data: a dict containing digital output for each signal, in m/s^2.
        Ex, {'in_accel_x': 0,
             'in_accel_y': 0,
             'in_accel_z': 9.8}

      orientations: a dict indicating the orentation in gravity
        (either 0 or -/+1) of the signal.
        Ex, {'in_accel_x': 0,
             'in_accel_y': 0,
             'in_accel_z': 1}
      spec_offset: a tuple of two integers, ex: (0.5, 0.5) indicating the
        tolerance for the digital output of sensors under zero gravity and
        one gravity, respectively.

    Returns:
      True if the data is within the tolerance of the spec.
    """
    for signal_name in data:
      value = data[signal_name]
      orientation = orientations[signal_name]
      # Check the sign of the value for -/+1G orientation.
      if orientation and orientation * value < 0:
        logging.error('The orientation of %s is wrong.', signal_name)
        return False
      # Check the abs value is within the range of -/+ offset.
      index = abs(orientation)
      ideal_value = _GRAVITY * orientation
      if abs(value - ideal_value) > spec_offset[index]:
        logging.error('Signal %s out of range: %f', signal_name, value)
        return False
    return True

  def CalculateCalibrationBias(self, data, orientations):
    # Calculating calibration data.
    calib_bias = {}
    for signal_name in data:
      ideal_value = _GRAVITY * orientations[signal_name]
      current_calib_bias = (
          int(self._GetSysfsValue('%s_calibbias' % signal_name))
          * _GRAVITY / 1024)
      # Calculate the difference between the ideal value and actual value
      # then store it into _calibbias.  In release image, the raw data will
      # be adjusted by _calibbias to generate the 'post-calibrated' values.
      calib_bias[signal_name + '_' + self.location + '_calibbias'] = (
          ideal_value - data[signal_name] + current_calib_bias)
    return calib_bias

  def UpdateCalibrationBias(self, calib_bias):
    """Update calibration bias to RO_VPD

    Args:
      A dict of calibration bias, in m/s^2.
      Ex, {'in_accel_x_base_calibbias': 0.1,
           'in_accel_y_base_calibbias': -0.2,
           'in_accel_z_base_calibbias': 0.3}
    """
    # Writes the calibration results into ro vpd.
    # The data is converted to 1/1024G unit before writing.
    logging.info('Calibration results: %s.', calib_bias)
    scaled = {k: str(int(v * 1024 / _GRAVITY)) for k, v in calib_bias.items()}
    self._device.vpd.ro.Update(scaled)
    mapping = []
    for signal_name in self.signal_names:
      mapping.append(('%s_%s_calibbias' % (signal_name, self.location),
                      '%s_calibbias' % signal_name))
    for vpd_entry, sysfs_entry in mapping:
      self._SetSysfsValue(sysfs_entry, scaled[vpd_entry])


class Accelerometer(device_types.DeviceComponent):
  """Accelerometer component module."""

  def GetController(self, location):
    """Gets a controller with specified arguments.

    See AccelerometerController for more information.
    """
    return AccelerometerController(self._device, 'cros-ec-accel', location)
