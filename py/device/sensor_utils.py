#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import time

import factory_common  # pylint: disable=W0611
from cros.factory.device import board
from cros.factory.device import component


_IIO_DEVICES_PATTERN = '/sys/bus/iio/devices/iio:device*'


def FindDevice(dut, path_pattern, **attr_filter):
  """Find device under given path.

  Args:
    path_pattern: The path to search, can contain wildcards.
    attr_filter: A filter to filter out unwanted devices.

  Returns:
    Path of the matched device.

  Raises:
    DUTException if not exactly one device found.
  """
  devices = []
  for path in dut.Glob(path_pattern):
    match = True
    for name, value in attr_filter.viewitems():
      try:
        if dut.ReadFile(dut.path.join(path, name)).strip() != value:
          match = False
          break
      except Exception:
        match = False
    if match:
      devices.append(path)

  if len(devices) == 0:
    raise board.DUTException(
        'Device with constraint %r not found' % attr_filter)
  elif len(devices) > 1:
    raise board.DUTException(
        'Multiple devices found with constraint %r' % attr_filter)

  return devices[0]


class BasicSensorController(component.DeviceComponent):
  """A sensor controller that only supports direct read."""

  def __init__(self, dut, name, location, signal_names):
    """Constructor.

    Args:
      dut: The DUT instance.
      name: The name attribute of sensor.
      location: The location attribute of sensor.
      signal_names: A list of signals to read.
    """
    super(BasicSensorController, self).__init__(dut)
    self.signal_names = signal_names
    self._iio_path = FindDevice(self._dut, _IIO_DEVICES_PATTERN,
                                name=name, location=location)

  def GetData(self, capture_count=1, sample_rate=20):
    """Reads several records of raw data and returns the average.

    Args:
      capture_count: how many records to read to compute the average.
      sample_rate: sample rate in Hz to read data from the sensor.

    Returns:
      A dict of the format {'signal_name': average value}
    """
    ret = {signal: 0 for signal in self.signal_names}
    for _ in xrange(capture_count):
      time.sleep(1.0 / sample_rate)
      for signal_name in ret:
        ret[signal_name] += float(self._dut.ReadFile(
            self._dut.path.join(self._iio_path, signal_name + '_raw')))
    for signal_name in ret:
      ret[signal_name] /= capture_count
    return ret
