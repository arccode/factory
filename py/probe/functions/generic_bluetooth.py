# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.probe import function
from cros.factory.probe.lib import cached_probe_function


def _ProbePCIOrUSB(path):
  path = os.path.abspath(os.path.realpath(path))
  return (function.InterpretFunction({'pci': path})() or
          function.InterpretFunction({'usb': os.path.join(path, '..')})())


def _RecursiveProbe(path, read_method):
  """Recursively probes in path and all the subdirectory using read_method.

  Args:
    path: Root path of the recursive probing.
    read_method: The method used to probe device information.
      This method accepts an input path and returns a string.
      e.g. _ReadSysfsUsbFields, _ReadSysfsPciFields, or _ReadSysfsDeviceId.

  Returns:
    A list of strings which contains probed results under path and
    all the subdirectory of path. Duplicated data will be omitted.
  """
  def _InternalRecursiveProbe(path, visited_path, results, read_method):
    """Recursively probes in path and all the subdirectory using read_method.

    Args:
      path: Root path of the recursive probing.
      visited_path: A set containing visited paths. These paths will not
        be visited again.
      results: A list of string which contains probed results.
        This list will be appended through the recursive probing.
      read_method: The method used to probe device information.
        This method accepts an input path and returns a string.

    Returns:
      No return value. results in the input will be appended with probed
      information. Duplicated data will be omitted.
    """
    path = os.path.realpath(path)
    if path in visited_path:
      return

    if os.path.isdir(path):
      data = read_method(path)
      # Only append new data
      for result in data:
        if result not in results:
          results.append(result)
      entries_list = os.listdir(path)
      visited_path.add(path)
    else:
      return

    for filename in entries_list:
      # Do not search directory upward
      if filename == 'subsystem':
        continue
      sub_path = os.path.join(path, filename)
      _InternalRecursiveProbe(sub_path, visited_path, results, read_method)
    return

  visited_path = set()
  results = []
  _InternalRecursiveProbe(path, visited_path, results, read_method)
  return results


class GenericBluetoothFunction(cached_probe_function.CachedProbeFunction):
  """Probe the generic Bluetooth information."""

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    # Probe in primary path
    device_id = _ProbePCIOrUSB('/sys/class/bluetooth/hci0/device')
    if device_id:
      return device_id

    # TODO(akahuang): Confirm if we only probe the primary path or not.
    # Use information in driver if probe failed in primary path
    device_id_list = _RecursiveProbe('/sys/module/bluetooth/holders',
                                     _ProbePCIOrUSB)
    return sorted([x for x in device_id_list if x])
