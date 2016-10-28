#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import math
import os
import re
import struct
import time
from collections import namedtuple

import factory_common  # pylint: disable=W0611
from cros.factory.device import component


_IIO_DEVICES_PATH = '/sys/bus/iio/devices/'
SYSFS_VALUE = namedtuple('sysfs_value', ['sysfs', 'value'])
IIO_SCAN_TYPE = namedtuple('IIO_SCAN_TYPE', ['endianness', 'sign', 'realbits',
                                             'storagebits', 'repeat', 'shift'])
_IIO_SCAN_TYPE_RE = re.compile(r'^(be|le):(s|u)(\d+)/(\d+)(?:X(\d+))?>>(\d+)$')


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


class AccelerometerController(component.DeviceComponent):
  """Utility class for the two accelerometers.

  Attributes:
    name: the name of the accelerometer, e.g., 'cros-ec-accel', or None.
      This will be used to lookup a matched name in
      /sys/bus/iio/devices/iio:deviceX/location to get
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
    super(AccelerometerController, self).__init__(board)
    self.trigger_number = '0'
    self.num_signals = 3  # (x, y, z).
    self.iio_bus_id = None
    self.location = location

    assert name is not None or location is not None
    for iio_path in glob.glob(os.path.join(_IIO_DEVICES_PATH, 'iio:device*')):
      if (name is not None and
          name != self._GetSysfsValue(os.path.join(iio_path, 'name'))):
        continue
      if (location is not None and
          location != self._GetSysfsValue(os.path.join(iio_path, 'location'))):
        continue

      self.iio_bus_id = os.path.basename(iio_path)
      break
    if self.iio_bus_id is None:
      raise AccelerometerException(
          'Accelerometer at (%r, %r) not found' % (self.name, self.location))
    scan_elements_path = os.path.join(
        _IIO_DEVICES_PATH, self.iio_bus_id, 'scan_elements')

    # 'in_accel_(x|y|z)_(base|lid)_index' contains a fixed value which
    # represents the so called scan order. After a capture is triggered,
    # the data will be dumped in a char file in the scan order.
    # Stores the (scan order -> signal name) mapping for later use.
    self.index_to_signal = {}
    for signal_name in self._GenSignalNames(''):
      index = int(self._dut.ReadFile(os.path.join(scan_elements_path,
                                                  signal_name + '_index')))
      scan_type = _ParseIIOBufferScanType(
          self._dut.ReadFile(os.path.join(scan_elements_path,
                                          signal_name + '_type')))
      self.index_to_signal[index] = dict(name=signal_name, scan_type=scan_type)

  def _GetSysfsValue(self, path):
    """Read the content of given path.

    Args:
      path: A string for file path to read.

    Returns:
      A string as stripped contents, or None if error.
    """
    try:
      return self._dut.ReadFile(path).strip()
    except Exception:
      pass

  def _SetSysfsValues(self, sysfs_values, check_call=True):
    """Assigns corresponding values to a list of sysfs.

    Args:
      A list of namedtuple SYSFS_VALUE containing the sysfs and
        it's corresponding value.
    """
    try:
      for sysfs_value in sysfs_values:
        self._dut.WriteFile(sysfs_value.sysfs, sysfs_value.value)
    except Exception:
      if check_call:
        raise

  def _GenSignalNames(self, postfix=''):
    """Generator function for all signal names.

    Args:
      postfix: a string that will be appended to each signal name.

    Returns:
      Strings: 'in_accel_(x|y|z)' + postfix.
    """
    for axis in ['x', 'y', 'z']:
      yield 'in_accel_' + axis + postfix

  def CleanUpCalibrationValues(self):
    """Clean up calibration values.

    The sysfs trigger only captures calibrated input values, so we reset
    the calibration to allow reading raw data from a trigger.
    """
    iio_bus_path = os.path.join(_IIO_DEVICES_PATH, self.iio_bus_id)
    for calibbias in self._GenSignalNames('_calibbias'):
      self._SetSysfsValues(
          [SYSFS_VALUE(os.path.join(iio_bus_path, calibbias), '0')])

  def GetRawDataAverage(self, capture_count=1, sample_rate=20):
    """Reads several records of raw data and returns the average.

    First, trigger the capture:
      echo 1 > /sys/bus/iio/devices/trigger0/trigger_now

    Then get the captured raw data from /dev/iio:deviceX.

    Args:
      capture_count: how many records to read to compute the average.
      sample_rate: sample rate in Hz to get raw data from accelerometers.

    Returns:
      A dict of the format {'signal_name': average value}
      Ex, {'in_accel_x': 4,
           'in_accel_y': 1,
           'in_accel_z': 1001}
    """
    # Each accelerometer raw data is 2 bytes and there are
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
    trigger_now_path = os.path.join(
        _IIO_DEVICES_PATH, 'trigger' + self.trigger_number, 'trigger_now')

    # Initializes the returned dict.
    ret = dict((signal_name, 0.0) for signal_name in self._GenSignalNames())
    # Reads the captured raw data.
    file_path = os.path.join('/dev/', self.iio_bus_id)
    raw_data_captured = 0
    retry_count_per_record = 0
    max_retry_count_per_record = 3
    while raw_data_captured < capture_count:
      self._SetSysfsValues([SYSFS_VALUE(trigger_now_path, '1')])
      # To prevent obtaining repeated data, add delay between each capture.
      # In addition, need to wait some time after set trigger_now to get
      # the raw data.
      time.sleep(1 / float(sample_rate))
      with open(file_path) as f:
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
                'GetRawDataAverage failed, exceeded maximum retry: %d)' %
                max_retry_count_per_record)
          logging.warning('Failed to read raw data (length=%d), '
                          'retry again (retry_count=%d).',
                          len(line), retry_count_per_record)
          continue
        raw_data_captured += 1
        retry_count_per_record = 0
        raw_data = struct.unpack_from(FORMAT_RAW_DATA, line)
        original_raw_data = {}
        # Accumulating raw data.
        for i in xrange(self.num_signals):
          name = self.index_to_signal[i]['name']
          scan_type = self.index_to_signal[i]['scan_type']
          original_raw_data[name] = raw_data[i] >> scan_type.shift
          ret[name] += original_raw_data[name]
        logging.info(
            '(%d) Getting raw data: %s.', raw_data_captured, original_raw_data)
    # Calculates the average
    for signal_name in ret:
      ret[signal_name] = int(round(ret[signal_name] / capture_count))
    logging.info('Average of %d raw data: %s', capture_count, ret)
    return ret

  def GetCalibratedDataAverage(self, capture_count=1, sample_rate=20):
    """Returns average values of the calibrated data.

    Args:
      capture_count: how many records to read to compute the average.
      sample_rate: sample rate in Hz to get raw data from accelerometers.

    Returns:
      A dict of the format {'signal_name': average value}
      Ex, {'in_accel_x': 1,
           'in_accel_y': -1,
           'in_accel_z': 1019}

    Raises:
      Raises AccelerometerException if there is no calibration
      value in VPD.
    """
    def _CalculateCalibratedValue(signal_name, value):
      calib_bias = int(ro_vpd[signal_name + '_' + self.location + '_calibbias'])
      return value + calib_bias

    # Get calibration data from VPD first.
    ro_vpd = self._dut.vpd.ro.GetAll()
    for calib_name in self._GenSignalNames('_' + self.location + '_calibbias'):
      if calib_name not in ro_vpd:
        raise AccelerometerException(
            'Calibration value: %r not found in RO_VPD.' % calib_name)

    # Get raw data and apply the calibration values on it.
    raw_data = self.GetRawDataAverage(capture_count, sample_rate)
    return dict(
        (k, _CalculateCalibratedValue(k, v)) for k, v in raw_data.iteritems())

  @staticmethod
  def IsWithinOffsetRange(raw_data, orientations, spec_ideal_values,
                          spec_offset):
    """Checks whether the value of raw data is within the spec or not.

    It is used before calibration to filter out abnormal accelerometers.

    Args:
      raw_data: a dict containing digital output for each signal.
        Ex, {'in_accel_x': 5,
             'in_accel_y': 21,
             'in_accel_z': 1004}

      orientations: a dict indicating the orentation in gravity
        (either 0 or -/+1) of the signal.
        Ex, {'in_accel_x': 0,
             'in_accel_y': 0,
             'in_accel_z': 1}
      spec_ideal_values: a tuple of two integers, ex (0, 1024) indicating
        the ideal value of the digitial output corresponding to zero gravity
        and one gravity, respectively.
      spec_offset: a tuple of two integers, ex: (128, 230) indicating the
        tolerance for the digital output of sensors under zero gravity and
        one gravity, respectively.

    Returns:
      True if the raw data is within the tolerance of the spec.
    """
    for signal_name in raw_data:
      value = raw_data[signal_name]
      orientation = orientations[signal_name]
      # Check the sign of the value for -/+1G orientation.
      if orientation and orientation * value < 0:
        logging.error('The orientation %d is wrong.', orientation)
        return False
      # Check the abs value is within the range of -/+ offset.
      index = abs(orientation)
      if abs(abs(value) - spec_ideal_values[index]) > spec_offset[index]:
        return False
    return True

  @staticmethod
  def IsGravityValid(raw_data, spec_ideal_value, spec_offset):
    """Checks whether the gravity value is within the spec or not.

    It is used before calibration to filter out abnormal accelerometers.

    Args:
      raw_data: a dict containing digital output for each signal.
        Ex, {'in_accel_x': 23,
             'in_accel_y': -19,
             'in_accel_z': 998}
      spec_ideal_value: ideal sensor value for 1G.
      spec_offset: tolerance for the digital output of sensors under 1G.

    Returns:
      True if the gravity is within the tolerance of the spec.
    """
    gravity_value = math.sqrt(sum(v * v for v in raw_data.viewvalues()))
    logging.info('Gravity value is: %d.', gravity_value)
    return abs(gravity_value - spec_ideal_value) < spec_offset

  def CalculateCalibrationBias(self, raw_data, orientation, spec_ideal_values):
    # Calculating calibration data.
    calib_bias = {}
    for signal_name in raw_data:
      index = abs(orientation[signal_name])
      ideal_value = spec_ideal_values[index]
      # For -1G, the ideal_value is -1024.
      if orientation[signal_name] == -1:
        ideal_value *= -1
      # Calculate the difference between the ideal value and actual value
      # then store it into _calibbias.  In release image, the raw data will
      # be adjusted by _calibbias to generate the 'post-calibrated' values.
      calib_bias[signal_name + '_' + self.location  + '_calibbias'] = str(
          ideal_value - raw_data[signal_name])
    return calib_bias

  def UpdateCalibrationBias(self, calib_bias):
    """Update calibration bias to RO_VPD

    Args:
      A dict of calibration bias
      Ex, {'in_accel_x_base_calibbias': 1,
           'in_accel_y_base_calibbias': -1,
           'in_accel_z_base_calibbias': 1019}
    """
    # Writes the calibration results into ro vpd.
    logging.info('Calibration results: %s.', calib_bias)
    self._dut.vpd.ro.Update(calib_bias)


class Accelerometer(component.DeviceComponent):
  """Accelerometer component module."""

  def GetController(self, location):
    """Gets a controller with specified arguments.

    See AccelerometerController for more information.
    """
    return AccelerometerController(self._dut, 'cros-ec-accel', location)
