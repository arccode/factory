# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.device import device_types
from cros.factory.device import sensor_utils


IN_COUNT = 'in_count_raw'
FREQUENCY = 'frequency'
DEFAULT_LOCATION = 'camera'


class VSyncSensorException(Exception):
  pass


class VSyncSensorController(sensor_utils.BasicSensorController):
  """Utility class for camera vertical sync sensor.

  Attributes:
    name: The name of the VSync sensor, e.g., 'cros-ec-sync', or None.
      This will be used to lookup a matched name in
      /sys/bus/iio/devices/iio:deviceX/name to get
      the corresponding iio:deviceX.
      At least one of name or location must present.

    location: The location of the VSync sensor, e.g., 'camera', or None.
      This will be used to lookup a matched location in
      /sys/bus/iio/devices/iio:deviceX/location to get
      the corresponding iio:deviceX.
      At least one of name or location must present.
  """

  def __init__(self, board, name, location):
    super(VSyncSensorController, self).__init__(
        board, name, location, [IN_COUNT, FREQUENCY])

  def _GetSysfsValue(self, filename, path=None):
    """Read the content of given path.  Overriding the one from parent
      to support raising exceptions.

    Args:
      filename: The name of the file to read.
      path: The path to read the given filename, default to the path
        of current iio device.

    Returns:
      A string as stripped contents, or raise exception if error.
    """
    if path is None:
      path = self._iio_path
    try:
      return self._device.ReadFile(os.path.join(path, filename)).strip()
    except Exception as e:
      raise VSyncSensorException(str(e))

  def GetCount(self):
    try:
      return int(self._GetSysfsValue(IN_COUNT))
    except Exception as e:
      raise VSyncSensorException("Failed to read count: %s" % str(e))

  def GetFrequency(self):
    try:
      return int(self._GetSysfsValue(FREQUENCY))
    except Exception as e:
      raise VSyncSensorException("Failed to read freq: %s" % str(e))

  def SetFrequency(self, freq):
    try:
      self._SetSysfsValue(FREQUENCY, str(freq))
    except Exception as e:
      raise VSyncSensorException("Failed to set freq: %s" % str(e))


class VSyncSensor(device_types.DeviceComponent):
  """Camera vertical sync sensor component module."""

  def GetController(self, location=DEFAULT_LOCATION):
    """Gets a controller with specified arguments.

    See sensor_utils.BasicSensorController for more information.
    """
    return VSyncSensorController(self._device, 'cros-ec-sync', location)
