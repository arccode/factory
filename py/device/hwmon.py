#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import pipes

import factory_common  # pylint: disable=W0611
from cros.factory.device import component


_HWMON_PATH = '/sys/class/hwmon'


class HardwareMonitorException(Exception):
  pass


class HardwareMonitorDevice(component.DeviceComponent):
  """A class representing a single hwmon device."""
  def __init__(self, dut, path):
    super(HardwareMonitorDevice, self).__init__(dut)
    self._path = path

  def GetAttribute(self, name):
    return self._dut.ReadFile(self._dut.path.join(self._path, name))

  def GetPath(self):
    return self._path


class HardwareMonitor(component.DeviceComponent):
  """Utility class for hardware monitor devices."""

  def __init__(self, dut, hwmon_path=_HWMON_PATH):
    super(HardwareMonitor, self).__init__(dut)
    self._hwmon_path = hwmon_path

  def FindOneDevice(self, attr_name, attr_value):
    """Search hwmon devices that have specified attribute name and value.

    Args:
      attr_name: An attribute name.
      attr_value: An attribute value.

    Returns:
      The matching hwmon device.

    Raises:
      HardwareMonitorException not exactly one device match the critiria.
    """
    devices = self.FindDevices(attr_name, attr_value)
    if len(devices) != 1:
      raise HardwareMonitorException('Not exactly one device match given'
                                     ' critiria')
    return devices[0]

  def FindDevices(self, attr_name, attr_value):
    """Search hwmon devices that have specified attribute name and value.

    Args:
      attr_name: An attribute name.
      attr_value: An attribute value.

    Returns:
      A list of matching hwmon device.
    """
    search_path = self._dut.path.join(self._hwmon_path, '*',
                                      pipes.quote(attr_name))
    output = self._dut.CheckOutput('grep %s -l -e %s' %
                                   (search_path,
                                    pipes.quote('^%s$' % attr_value)))
    return [HardwareMonitorDevice(self._dut, self._dut.path.dirname(path))
            for path in output.splitlines()]
