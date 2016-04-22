#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os.path
import time

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


_IIO_DEVICES_PATH = '/sys/bus/iio/devices/'


class GyroscopeException(Exception):
  pass


class GyroscopeController(component.DUTComponent):
  """Base class for gyroscope component module."""

  def __init__(self, dut, name, location, sample_rate):
    """Constructor.

    Args:
      dut: The DUT instance.
      name: The name attribute of gyro.
      location: The location attribute of gyro.
      sample_rate: Sample rate in Hz to get raw data.
    """
    super(GyroscopeController, self).__init__(dut)
    self._iio_path = None
    self._sample_rate = sample_rate
    for iio_path in glob.glob(os.path.join(_IIO_DEVICES_PATH, 'iio:device*')):
      try:
        iio_name = self._dut.ReadFile(os.path.join(iio_path, 'name'))
        iio_location = self._dut.ReadFile(os.path.join(iio_path, 'location'))
      except component.CalledProcessError:
        continue
      if name == iio_name.strip() and location == iio_location.strip():
        self._iio_path = iio_path
    if self._iio_path is None:
      raise GyroscopeException('Gyroscope at %s not found' % location)

  def GetRawDataAverage(self, capture_count=1):
    """Reads several records of raw data and returns the average.

    Args:
      capture_count: how many records to read to compute the average.

    Returns:
      A dict of the format {'signal_name': average value}
    """
    ret = {'in_anglvel_x_raw': 0,
           'in_anglvel_y_raw': 0,
           'in_anglvel_z_raw': 0}
    for _ in xrange(capture_count):
      time.sleep(1 / float(self._sample_rate))
      for signal_name in ret:
        ret[signal_name] += float(self._dut.ReadFile(os.path.join(self._iio_path,
                                                                  signal_name)))
    for signal_name in ret:
      ret[signal_name] /= capture_count
    return ret


class Gyroscope(component.DUTComponent):
  """Gyroscope component module."""

  def GetController(self, name='cros-ec-gyro', location='base', sample_rate=60):
    """Gets a controller with specified arguments.

    See GyroscopeController for more information.
    """
    return GyroscopeController(self._dut, name, location, sample_rate)
