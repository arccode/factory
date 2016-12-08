# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import re

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


INPUT_DEVICE_PATH = '/proc/bus/input/devices'


def GetInputDevices():
  """Returns all input devices connected to the machine."""
  dataset = []
  data = {}
  entry = None
  with open(INPUT_DEVICE_PATH) as f:
    for line in f:
      prefix = line[0]
      content = line[3:].strip()
      # Format: PREFIX: Key=Value
      #  I: Bus=HHHH Vendor=HHHH Product=HHHH Version=HHHH
      #  N: Name="XXXX"
      #  P: Phys=XXXX
      #  S: Sysfs=XXXX
      if prefix == 'I':
        if data:
          dataset.append(data)
        data = {}
        for entry in content.split():
          key, value = entry.split('=', 1)
          data[key.lower()] = value
      elif prefix in ['N', 'S']:
        key, value = content.split('=', 1)
        data[key.lower()] = value.strip('"')
      elif prefix == 'H':
        for handler in line[3:].split('=', 1)[1].split():
          if re.match(r'event\d+', handler):
            data['event'] = handler
            break

    # Flush output.
    if data:
      dataset.append(data)
  return dataset


class InputDeviceFunction(function.ProbeFunction):
  """Probes the information of input devices.

  This function gets information of all input devices connected to the machine,
  and then filters the results by the given arguments.
  """

  ARGS = [
      Arg('vendor', str, 'The vendor ID.', optional=True),
      Arg('product', str, 'The product ID.', optional=True),
      Arg('name', str, 'The name of the device.', optional=True),
  ]

  def Probe(self):
    devices = GetInputDevices()
    for field in ['vendor', 'product', 'name']:
      devices = self.FilterBy(devices, field, getattr(self.args, field))
    return devices

  def FilterBy(self, devices, field, value):
    """Filters for the devices whose fields are equal to certain values."""
    if value is None:
      return devices
    return [device for device in devices if device.get(field) == value]
