#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import math
import os
import struct
import time
from collections import namedtuple

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, SpawnOutput


_IIO_DEVICES_PATH = '/sys/bus/iio/devices/'
_ACCELEROMETER_DEVICES_PATH = '/dev/cros-ec-accel'
SYSFS_VALUE = namedtuple('sysfs_value', ['sysfs', 'value'])


class AccelerometerControllerException(Exception):
  pass


class AccelerometerController(object):
  """Utility class for the two accelerometers.

  Attributes:
    spec_offset: A tuple of two integers, ex: (128, 230) indicating the
      tolerance for the digital output of sensors under zero gravity and
      one gravity, respectively.
    spec_ideal_values: A tuple of two integers, ex (0, 1024) indicating
      the ideal value of the digitial output corresponding to zero gravity
      and one gravity, respectively.
    sample_rate: Sample rate in Hz to get raw data from accelerometers.

  Raises:
    Raises AccelerometerControllerException if there is no accelerometer.
  """

  def __init__(self, spec_offset, spec_ideal_values, sample_rate):
    """Cleans up previous calibration values and stores the scan order.

    We can get raw data from below sysfs:
      /sys/bus/iio/devices/iio:deviceX/in_accel_(x|y|z)_(base|lid)_raw.

    However, there is no guarantee that the data will have been sampled
    at the same time. We can use existing triggers (see below CL) to get
    simultaneous raw data from /dev/iio:deviceX ordered by
    in_accel_(x|y|z)_(base|lid)_index.

    https://chromium-review.googlesource.com/#/c/190471/.
    """
    if not os.path.exists(_ACCELEROMETER_DEVICES_PATH):
      raise AccelerometerControllerException('Accelerometer not found')
    self.trigger_number = '0'
    self.num_signals = 2 * 3 # Two sensors * (x, y, z).
    self.iio_bus_id = os.readlink(_ACCELEROMETER_DEVICES_PATH)
    self.spec_offset = spec_offset
    self.spec_ideal_values = spec_ideal_values
    self.sample_rate = sample_rate

    scan_elements_path = os.path.join(
        _IIO_DEVICES_PATH, self.iio_bus_id, 'scan_elements')

    self._CleanUpCalibrationValues()

    # 'in_accel_(x|y|z)_(base|lid)_index' contains a fixed value which
    # represents the so called scan order. After a capture is triggered,
    # the data will be dumped in a char file in the scan order.
    # Stores the (scan order -> signal name) mapping for later use.
    self.index_to_signal_name = {}
    for signal_name in self._GenSignalNames(''):
      index = int(SpawnOutput(
          ['cat', os.path.join(scan_elements_path, signal_name + '_index')],
          log=True))
      self.index_to_signal_name[index] = signal_name

  def _SetSysfsValues(self, sysfs_values, check_call=True):
    """Assigns corresponding values to a list of sysfs.

    Args:
      A list of namedtuple SYSFS_VALUE containing the sysfs and
        it's corresponding value.
    """
    for sysfs_value in sysfs_values:
      Spawn('echo %s > %s' % (sysfs_value.value, sysfs_value.sysfs),
            shell=True, sudo=True, log=True, check_call=check_call)

  def _GenSignalNames(self, postfix=''):
    """Generator function for all signal names.

    Args:
      postfix: a string that will be appended to each signale name.

    Returns:
      Strings: 'in_accel_(x|y|z)_(base|lid)_' + postfix.
    """
    for location in ['base', 'lid']:
      for axis in ['x', 'y', 'z']:
        yield 'in_accel_' + axis + '_' + location + postfix

  def _CleanUpCalibrationValues(self):
    """Clean up calibration values.

    The sysfs trigger only captures calibrated input values, so we reset
    the calibration to allow reading raw data from a trigger.
    """
    iio_bus_path = os.path.join(_IIO_DEVICES_PATH, self.iio_bus_id)
    for calibbias in self._GenSignalNames('_calibbias'):
      self._SetSysfsValues(
          [SYSFS_VALUE(os.path.join(iio_bus_path, calibbias), '0')])
    for calibscale in self._GenSignalNames('_calibscale'):
      self._SetSysfsValues([SYSFS_VALUE(
          os.path.join(iio_bus_path, calibscale),
                       str(self.spec_ideal_values[1]))])

  def GetRawDataAverage(self, capture_count=1):
    """Reads several records of raw data and returns the average.

    First, trigger the capture:
      echo 1 > /sys/bus/iio/devices/trigger0/trigger_now

    Then get the captured raw data from /dev/iio:deviceX.

    Args:
      capture_count: how many records to read to compute the average.

    Returns:
      A dict of the format {'signal_name': average value}
      Ex, {'in_accel_x_base': 4,
           'in_accel_y_base': 1,
           'in_accel_z_base': 1001,
           'in_accel_x_lid': -3,
           'in_accel_y_lid': 32,
           'in_accel_z_lid': -999}
    """
    # Each accelerometer raw data is 2 bytes and there are
    # 6 signals, so the buffer lenght of one record is 12 bytes.
    # The default order is in_accel_(x|y|z)_base, in_accel_(x|y|z)_lid.
    #  0 1 2 3 4 5 6 7 8 9 0 1
    # +-+-+-+-+-+-+-+-+-+-+-+-+
    # | x | y | z | x | y | z |
    # +-+-+-+-+-+-+-+-+-+-+-+-+
    buffer_length_per_record = 12
    FORMAT_RAW_DATA = '<6h'
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
      time.sleep(1 / float(self.sample_rate))
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
            raise AccelerometerControllerException(
                'GetRawDataAverage failed, exceeded maximum retry: %d)' %
                max_retry_count_per_record)
          logging.warning('Failed to read raw data (length=%d), '
                          'retry again (retry_count=%d).',
                          len(line), retry_count_per_record)
          continue
        raw_data_captured += 1
        retry_count_per_record = 0
        raw_data = struct.unpack_from(FORMAT_RAW_DATA, line)
        logging.info('(%d) Getting raw data: %s.', raw_data_captured, raw_data)
        # Accumulating raw data.
        for i in xrange(self.num_signals):
          ret[self.index_to_signal_name[i]] += raw_data[i]
    # Calculates the average
    for signal_name in ret:
      ret[signal_name] = int(round(ret[signal_name] / capture_count))
    logging.info('Average of %d raw data: %s', capture_count, ret)
    return ret

  def IsWithinOffsetRange(self, raw_data, orientations):
    """Checks whether the value of raw data is within the spec or not.

    It is used before calibration to filter out abnormal accelerometers.

    Args:
      raw_data: a dict containing digital output for each signal.
        Ex, {'in_accel_x_base': 5,
             'in_accel_y_base': 21,
             'in_accel_z_base': 1004,
             'in_accel_x_lid': -39,
             'in_accel_y_lid': 12,
             'in_accel_z_lid': -998}

      orientations: a dict indicating the orentation in gravity
        (either 0 or -/+1) of the signal.
        Ex, {'in_accel_x_base': 0,
             'in_accel_y_base': 0,
             'in_accel_z_base': 1,
             'in_accel_x_lid': 0,
             'in_accel_y_lid': 0,
             'in_accel_z_lid': -1}
    Returns:
      True if the raw data is within the tolerance of the spec.
    """
    if set(raw_data) != set(orientations) or len(raw_data) != self.num_signals:
      logging.error('The size of raw data or orientations is wrong.')
      return False
    for signal_name in raw_data:
      value = raw_data[signal_name]
      orientation = orientations[signal_name]
      # Check the sign of the value for -/+1G orientation.
      if orientation and orientation * value < 0:
        logging.error('The orientation %d is wrong.', orientation)
        return False
      # Check the abs value is within the range of -/+ offset.
      index = abs(orientation)
      if (abs(value) < self.spec_ideal_values[index] - self.spec_offset[index]
          or
          abs(value) > self.spec_ideal_values[index] + self.spec_offset[index]):
        return False
    return True

  def IsGravityValid(self, raw_data):
    """Checks whether the gravity value is within the spec or not.

    It is used before calibration to filter out abnormal accelerometers.

    Args:
      raw_data: a dict containing digital output for each signal.
        Ex, {'in_accel_x_base': 23,
             'in_accel_y_base': -19,
             'in_accel_z_base': 998,
             'in_accel_x_lid': 12,
             'in_accel_y_lid': 21,
             'in_accel_z_lid': -1005}
    Returns:
      True if the gravity is within the tolerance of the spec.
    """
    for location in ['base', 'lid']:
      (x, y, z) = (raw_data['in_accel_x_' + location],
                   raw_data['in_accel_y_' + location],
                   raw_data['in_accel_z_' + location])
      gravity_value = math.sqrt(x * x + y * y + z * z)
      logging.info('Gravity value at %s is: %d.', location, gravity_value)
      if (gravity_value < self.spec_ideal_values[1] - self.spec_offset[1] or
          gravity_value > self.spec_ideal_values[1] + self.spec_offset[1]):
        return False
    return True
