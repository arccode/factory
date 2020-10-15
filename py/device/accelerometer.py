# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from collections import namedtuple
import logging
import os
import re
import struct
import time

from cros.factory.device import device_types
from cros.factory.device import sensor_utils


_IIO_DEVICES_PATH = '/sys/bus/iio/devices/'
IIO_SCAN_TYPE = namedtuple('IIO_SCAN_TYPE', ['endianness', 'sign', 'realbits',
                                             'storagebits', 'repeat', 'shift'])
_IIO_SCAN_TYPE_RE = re.compile(r'^(be|le):(s|u)(\d+)/(\d+)(?:X(\d+))?>>(\d+)$')
_GRAVITY = 9.80665

def _ParseIIOBufferScanType(type_str):
  """Parse IIO buffer type from a string.
  See https://www.kernel.org/doc/htmldocs/iio/iiobuffer.html for detailed spec.

  Args:
    type_str: A string describing channel spec, e.g. 'le:s12/16>>4'.

  Returns:
    Parsed result of type IIO_SCAN_TYPE.
  """
  match = _IIO_SCAN_TYPE_RE.match(type_str)
  if not match:
    raise ValueError('Invalid channel spec string: %s' % type_str)
  endianness = match.group(1)
  sign = match.group(2)
  realbits = int(match.group(3))
  storagebits = int(match.group(4))
  repeat = int(match.group(5)) if match.group(5) else None
  shift = int(match.group(6))
  return IIO_SCAN_TYPE(endianness, sign, realbits, storagebits, repeat, shift)


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
    at the same time. We can use existing triggers (see below CL) to get
    simultaneous raw data from /dev/iio:deviceX ordered by
    in_accel_(x|y|z)_index.

    https://chromium-review.googlesource.com/#/c/190471/.
    """
    super(AccelerometerController, self).__init__(
        board, name, location, ['in_accel_x', 'in_accel_y', 'in_accel_z'],
        scale=True)
    self.num_signals = 3  # (x, y, z).
    self.location = location
    self.trigger_path = None

    self.iio_bus_id = self._device.path.basename(self._iio_path)

    trigger_name = self._GetSysfsValue('trigger/current_trigger')
    self.trigger_path = sensor_utils.FindDevice(
        self._device, self._device.path.join(_IIO_DEVICES_PATH, 'trigger*'),
        name=trigger_name)

    scan_elements_path = os.path.join(
        _IIO_DEVICES_PATH, self.iio_bus_id, 'scan_elements')

    # 'in_accel_(x|y|z)_(base|lid)_index' contains a fixed value which
    # represents the so called scan order. After a capture is triggered,
    # the data will be dumped in a char file in the scan order.
    # Stores the (scan order -> signal name) mapping for later use.
    self.index_to_signal = {}
    for signal_name in self.signal_names:
      index = int(
          self._GetSysfsValue('%s_index' % signal_name, scan_elements_path))
      scan_type = _ParseIIOBufferScanType(
          self._GetSysfsValue('%s_type' % signal_name, scan_elements_path))
      self.index_to_signal[index] = dict(name=signal_name, scan_type=scan_type)

  def CleanUpCalibrationValues(self):
    """Clean up calibration values.

    The sysfs trigger only captures calibrated input values, so we reset
    the calibration to allow reading raw data from a trigger.
    """
    for signal_name in self.signal_names:
      self._SetSysfsValue('%s_calibbias' % signal_name, '0')

  def GetData(self, capture_count=1, sample_rate=20):
    """Returns average values of the sensor data.

    First, trigger the capture:
      echo 1 > /sys/bus/iio/devices/trigger0/trigger_now

    Then get the captured data from /dev/iio:deviceX.

    Args:
      capture_count: how many records to read to compute the average.
      sample_rate: sample rate in Hz to read data from accelerometers.

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
    # Each accelerometer data is 2 bytes and there are
    # 3 signals, so the buffer lenght of one record is 6 bytes.
    # The default order is in_accel_(x|y|z).
    #  0 1 2 3 4 5
    # +-+-+-+-+-+-+
    # | x | y | z |
    # +-+-+-+-+-+-+
    # TODO(phoenixshen): generate the struct from scan_type instead of using
    # hardcoded values

    buffer_length_per_record = 6
    FORMAT_RAW_DATA = '<3h'

    # Initializes the returned dict.
    ret = {signal_name: 0.0 for signal_name in self.signal_names}
    # Reads the captured data.
    file_path = os.path.join('/dev/', self.iio_bus_id)
    data_captured = 0
    retry_count_per_record = 0
    max_retry_count_per_record = 3
    while data_captured < capture_count:
      self._SetSysfsValue('trigger_now', '1', path=self.trigger_path)
      # To prevent obtaining repeated data, add delay between each capture.
      # In addition, need to wait some time after set trigger_now to get
      # the raw data.
      time.sleep(1 / sample_rate)
      with open(file_path, 'rb') as f:
        line = f.read(buffer_length_per_record)
        # Sometimes it fails to read a record of raw data (12 bytes) because
        # Chrome is reading the data at the same time.
        # Use a retry here but we should figure out how to stop Chrome
        # from reading.
        # TODO(bowgotsai): Stop Chrome from reading the raw data.
        if len(line) != buffer_length_per_record:
          retry_count_per_record += 1
          # To prevent indefinitely reading raw data if there is a real problem.
          if retry_count_per_record > max_retry_count_per_record:
            raise AccelerometerException(
                'GetData failed, exceeded maximum retry: %d)' %
                max_retry_count_per_record)
          logging.warning('Failed to read data (length=%d), '
                          'retry again (retry_count=%d).',
                          len(line), retry_count_per_record)
          continue
        data_captured += 1
        retry_count_per_record = 0
        raw_data = struct.unpack_from(FORMAT_RAW_DATA, line)
        original_raw_data = {}
        # Accumulating.
        for i in range(self.num_signals):
          name = self.index_to_signal[i]['name']
          scan_type = self.index_to_signal[i]['scan_type']
          original_raw_data[name] = raw_data[i] >> scan_type.shift
          ret[name] += original_raw_data[name]
        logging.info(
            '(%d) Getting data: %s.', data_captured, original_raw_data)
    # Calculates average value and convert to SI unit.
    for signal_name in ret:
      ret[signal_name] = (
          int(round(ret[signal_name] / capture_count)) * self.scale)
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
