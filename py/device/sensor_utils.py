# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import time

from six.moves import xrange
from six import viewitems

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types


_IIO_DEVICES_PATTERN = '/sys/bus/iio/devices/iio:device*'


def FindDevice(dut, path_pattern, **attr_filter):
  """Find device under given path.

  Args:
    path_pattern: The path to search, can contain wildcards.
    attr_filter: A filter to filter out unwanted devices.

  Returns:
    Path of the matched device.

  Raises:
    DeviceException if not exactly one device found.
  """
  devices = []
  for path in dut.Glob(path_pattern):
    match = True
    for name, value in viewitems(attr_filter):
      try:
        if dut.ReadSpecialFile(dut.path.join(path, name)).strip() != value:
          match = False
          break
      except Exception:
        match = False
    if match:
      devices.append(path)

  if not devices:
    raise types.DeviceException(
        'Device with constraint %r not found' % attr_filter)
  elif len(devices) > 1:
    raise types.DeviceException(
        'Multiple devices found with constraint %r' % attr_filter)

  return devices[0]


class BasicSensorController(types.DeviceComponent):
  """A sensor controller that only supports direct read."""

  def __init__(self, dut, name, location, signal_names, scale=False):
    """Constructor.

    Args:
      dut: The DUT instance.
      name: The name attribute of sensor.
      location: The location attribute of sensor.
      signal_names: A list of signals to read.
      scale: Whether to scale the return value.
    """
    super(BasicSensorController, self).__init__(dut)
    self.signal_names = signal_names
    self._iio_path = FindDevice(self._device, _IIO_DEVICES_PATTERN,
                                name=name, location=location)
    self.scale = 1.0 if not scale else float(self._GetSysfsValue('scale'))

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
      path = self._iio_path
    try:
      return self._device.ReadFile(os.path.join(path, filename)).strip()
    except Exception:
      pass

  def _SetSysfsValue(self, filename, value, check_call=True, path=None):
    """Assigns corresponding values to a list of sysfs.

    Args:
      filename: name of the file to write.
      value: the value to be write.
      path: Path to write the given filename, default to the path of
        current iio device.
    """
    if path is None:
      path = self._iio_path
    try:
      self._device.WriteFile(os.path.join(path, filename), value)
    except Exception:
      if check_call:
        raise

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
        ret[signal_name] += float(self._GetSysfsValue(signal_name + '_raw'))
    for signal_name in ret:
      ret[signal_name] *= self.scale
      ret[signal_name] /= capture_count
    return ret
