# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import sysfs
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils

from cros.factory.external import evdev


INPUT_DEVICE_PATH = '/proc/bus/input/devices'
KNOWN_DEVICE_TYPES = type_utils.Enum(['touchscreen', 'touchpad', 'stylus'])


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


def GetDeviceType(device):
  evdev_device = evdev.InputDevice(os.path.join('/dev/input', device['event']))
  ret = 'unknown'
  if evdev_utils.IsStylusDevice(evdev_device):
    ret = KNOWN_DEVICE_TYPES.stylus
  if evdev_utils.IsTouchpadDevice(evdev_device):
    ret = KNOWN_DEVICE_TYPES.touchpad
  if evdev_utils.IsTouchscreenDevice(evdev_device):
    ret = KNOWN_DEVICE_TYPES.touchscreen
  logging.debug('device %s type: %s', device['event'], ret)
  return ret


class InputDeviceFunction(function.ProbeFunction):
  """Probes the information of input devices.

  This function gets information of all input devices connected to the machine,
  and then filters the results by the given arguments.
  """

  ARGS = [
      Arg('device_type', str, 'The type of input device. '
          'One of "touchscreen", "touchpad", "stylus".', optional=True),
      Arg('sysfs_files', list, 'The files in the sysfs node.', optional=True),
  ]

  def Probe(self):
    devices = GetInputDevices()
    if self.args.device_type is not None:
      assert self.args.device_type in KNOWN_DEVICE_TYPES
      devices = [device for device in devices
                 if GetDeviceType(device) == self.args.device_type]
    if self.args.sysfs_files:
      for device in devices:
        self.AddSysfsFields(device)
    return devices

  def AddSysfsFields(self, device):
    sysfs_path = os.path.join('/sys', device['sysfs'].lstrip('/'), 'device')
    fields = sysfs.ReadSysfs(sysfs_path, self.args.sysfs_files)
    if fields:
      device.update(fields)
