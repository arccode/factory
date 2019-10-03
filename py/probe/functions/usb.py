# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re

from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


REQUIRED_FIELDS = ['idVendor', 'idProduct']
OPTIONAL_FIELDS = ['manufacturer', 'product', 'bcdDevice']


def ReadUSBSysfs(dir_path):
  result = sysfs.ReadSysfs(
      dir_path, REQUIRED_FIELDS, optional_keys=OPTIONAL_FIELDS)
  if result:
    result['bus_type'] = 'usb'
  return result


class USBFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Probes all usb devices listed in the sysfs ``/sys/bus/usb/devices/``.

  Description
  -----------
  This function goes through ``/sys/bus/usb/devices/`` to read attributes of
  each usb device (also includes usb root hub) listed there.  Each result
  should contain these fields:

  - ``device_path``: Pathname of the sysfs directory.
  - ``idVendor``
  - ``idProduct``

  The result might also contain these optional fields if they are exported in
  the sysfs entry:

  - ``manufacturer``
  - ``product``
  - ``bcdDevice``

  Examples
  --------
  Let's say the Chromebook has two usb devices.  One of which
  (at ``/sys/bus/usb/devices/1-1``) has the attributes:

  - ``idVendor=0x0123``
  - ``idProduct=0x4567``
  - ``manufacturer=Google``
  - ``product=Google Fancy Camera``
  - ``bcdDevice=0x8901``

  And the other one (at ``/sys/bus/usb/devices/1-2``) has the attributes:

  - ``idVendor=0x0246``
  - ``idProduct=0x1357``
  - ``product=Goofy Bluetooth``

  Then the probe statement::

    {
      "eval": "usb"
    }

  will have the corresponding probed result::

    [
      {
        "bus_type": "usb",
        "idVendor": "0123",
        "idProduct": "4567",
        "manufacturer": "Google",
        "product": "Google Fancy Camera",
        "bcdDevice": "8901"
      },
      {
        "bus_type": "usb",
        "idVendor": "0246",
        "idProduct": "1357",
        "product": "Goofy Bluetooth"
      }
    ]

  To verify if the Chromebook has Google Fancy Camera or not, you can write
  a probe statement like::

    {
      "eval": "usb",
      "expect": {
        "idVendor": "0123",
        "idProduct": "4567"
      }
    }

  and verify if the ``camera`` field of the probed result dict contains
  elements or not.

  You can also specify ``dir_path`` argument directly to ask the function
  to probe that sysfs USB entry.  For example, the probe statement ::

    {
      "eval": "usb:/sys/bus/usb/devices/1-1"
    }

  will have the corresponding probed results::

    [
      {
        "bus_type": "usb",
        "idVendor": "0123",
        ...
      }
    ]
  """
  GLOB_PATH = '/sys/bus/usb/devices/*'

  @classmethod
  def ProbeDevice(cls, dir_path):
    # A valid usb device name is <roothub_num>-<addr>[.<addr2>[.<addr3>...]] or
    # usb[0-9]+ for usb root hub.
    name = os.path.basename(dir_path)
    if (not re.match(r'^[0-9]+-[0-9]+(\.[0-9]+)*$', name) and
        not re.match(r'^usb[0-9]+$', name)):
      return None

    return ReadUSBSysfs(dir_path)
