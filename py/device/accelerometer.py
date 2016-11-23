#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
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
    self.num_signals = 3  # (x, y, z).
    self.iio_bus_id = None
    self.iio_bus_path = None
    self.location = location
    self.trigger_path = None

    assert name is not None or location is not None
    for iio_path in glob.glob(os.path.join(_IIO_DEVICES_PATH, 'iio:device*')):
      if (name is not None and
          name != self._GetSysfsValue('name', path=iio_path)):
        continue
      if (location is not None and
          location != self._GetSysfsValue('location', path=iio_path)):
        continue

      self.iio_bus_id = os.path.basename(iio_path)
      self.iio_bus_path = os.path.join(_IIO_DEVICES_PATH, self.iio_bus_id)
      break
    if self.iio_bus_id is None:
      raise AccelerometerException(
          'Accelerometer at (%r, %r) not found' % (self.name, self.location))

    trigger_name = self._GetSysfsValue('trigger/current_trigger')
    for iio_path in glob.glob(os.path.join(_IIO_DEVICES_PATH, 'trigger*')):
      if trigger_name == self._GetSysfsValue('name', path=iio_path):
        self.trigger_path = iio_path
        break
    if self.trigger_path is None:
      raise AccelerometerException('Trigger not found')

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

  def _GetSysfsValue(self, filename, path=None):
    """Read the content of given path.

    Args:
      filename: name of the file to read.
      path: Path to read the given filename, default to the path of
        current iio device.

    Returns:
      A string as stripped contents, or None if error.
    """
    if path is None:
      path = self.iio_bus_path
    try:
      return self._dut.ReadFile(os.path.join(path, filename)).strip()
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
    for calibbias in self._GenSignalNames('_calibbias'):
      self._SetSysfsValues(
          [SYSFS_VALUE(os.path.join(self.iio_bus_path, calibbias), '0')])

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
    trigger_now_path = os.path.join(self.trigger_path, 'trigger_now')

    # Initializes the returned dict.
    ret = dict((signal_name, 0.0) for signal_name in self._GenSignalNames())
    # Reads the captured data.
    file_path = os.path.join('/dev/', self.iio_bus_id)
    data_captured = 0
    retry_count_per_record = 0
    max_retry_count_per_record = 3
    while data_captured < capture_count:
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
        for i in xrange(self.num_signals):
          name = self.index_to_signal[i]['name']
          scan_type = self.index_to_signal[i]['scan_type']
          original_raw_data[name] = raw_data[i] >> scan_type.shift
          ret[name] += original_raw_data[name]
        logging.info(
            '(%d) Getting data: %s.', data_captured, original_raw_data)
    # Calculates average value and convert to SI unit.
    scale = float(self._GetSysfsValue('scale'))
    for signal_name in ret:
      ret[signal_name] = int(round(ret[signal_name] / capture_count)) * scale
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
      current_calib_bias = int(self._GetSysfsValue(
          '%s_calibbias' % signal_name))
      # Calculate the difference between the ideal value and actual value
      # then store it into _calibbias.  In release image, the raw data will
      # be adjusted by _calibbias to generate the 'post-calibrated' values.
      calib_bias[signal_name + '_' + self.location  + '_calibbias'] = (
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
    scaled = dict((k, str(int(v * 1024 / _GRAVITY)))
                  for k, v in calib_bias.viewitems())
    self._dut.vpd.ro.Update(scaled)


class Accelerometer(component.DeviceComponent):
  """Accelerometer component module."""

  def GetController(self, location):
    """Gets a controller with specified arguments.

    See AccelerometerController for more information.
    """
    return AccelerometerController(self._dut, 'cros-ec-accel', location)
