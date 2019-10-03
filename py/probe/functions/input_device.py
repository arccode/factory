# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re

from cros.factory.probe.lib import cached_probe_function
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


class InputDeviceFunction(cached_probe_function.CachedProbeFunction):
  """Probes the information of input devices.

  Description
  -----------
  This function gets information of all input devices connected to the machine
  by parsing the file ``/proc/bus/input/devices``, and then filters the results
  by the given arguments.

  The probed result for one input device is a dictionary which contains
  following fields:

  - ``product``: The product code in a string of 16-bits hex number.
  - ``vendor``: The vendor code in a string of 16-bits hex number.
  - ``version``: The version number in a string of 16-bits hex number.
  - ``name``: The name of the device.
  - ``bus``: The bus number in a string of 16-bits hex number.
  - ``sysfs``: The pathname of the sysfs entry of that device.
  - ``event``

  Because values in ``/proc/bus/input/devices`` are exported by the driver of
  each input device, an input device can not be probed correctly by this
  function if its driver doesn't export correct values.

  Examples
  --------
  Without specifying the device type, the probe statement ::

    {
      "eval": "input_device"
    }

  will have the corresponding probed results like ::

    [
      {
        "product": "3043",
        "version": "0100",
        "vendor": "2345",
        "name": "Google Inc. XXYY",
        "bus": "0003",
        "sysfs": "/devices/pci0000:00/0000:00:34.0/usb3/......",
        "event": "event3"
      },
      {
        "product": "3044",
        "version": "0001",
        "vendor": "2347",
        "name": "elgooG Inc. AABB",
        "bus": "0002",
        "sysfs": "/devices/pci0000:00/0000:00:32.0/usb3/......",
        "event": "event1"
      },
      ...
    ]

  To strict the probe results to ``touchscreen`` type, the probe statement
  is::

    {
      "eval": "input_device:touchscreen"
    }
  """

  ARGS = [
      Arg('device_type', KNOWN_DEVICE_TYPES, 'The type of input device.',
          default=None)
  ]

  def GetCategoryFromArgs(self):
    if (self.args.device_type is not None and
        self.args.device_type not in KNOWN_DEVICE_TYPES):
      raise cached_probe_function.InvalidCategoryError(
          'The type of input device must be one of %r' % KNOWN_DEVICE_TYPES)

    return self.args.device_type

  @classmethod
  def ProbeAllDevices(cls):
    ret = {}
    for dev in GetInputDevices():
      ret.setdefault(GetDeviceType(dev), []).append(dev)
    return ret
