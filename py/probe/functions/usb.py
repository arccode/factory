# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re

import factory_common  # pylint: disable=unused-import
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
  """Reads the USB sysfs structure.

  Each result should contain these fields:
    idVendor
    idProduct
  The result might also contain these optional fields:
    manufacturer
    product
    bcdDevice
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
