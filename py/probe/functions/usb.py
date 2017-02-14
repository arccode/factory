# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import sysfs
from cros.factory.utils.arg_utils import Arg


class USBFunction(function.ProbeFunction):
  """Reads the USB sysfs structure.

  Each result should contain these fields:
    idVendor
    idProduct
  The result might also contain these optional fields:
    manufacturer
    product
    bcdDevice
  """

  ARGS = [
      Arg('dir_path', str, 'The path used to search for USB sysfs data. '
          'First all symlinks are resolved, to the the "real" path. Then '
          'iteratively search toward parent folder until the remaining path '
          'contains the relevent data fields.'),
  ]

  REQUIRED_FIELDS = ['idVendor', 'idProduct']
  OPTIONAL_FIELDS = ['manufacturer', 'product', 'bcdDevice']

  def Probe(self):
    ret = []
    for path in glob.glob(self.args.dir_path):
      path = os.path.realpath(path)
      # The path of USB sysfs node should contain "/usb*" folder.
      # Example: /sys/devices/pci0000:00/0000:00:09.0/usb2/2-1
      while path.find('/usb') > 0:
        if os.path.exists(os.path.join(path, 'idProduct')):
          break
        path = os.path.dirname(path)

      result = sysfs.ReadSysfs(path, self.REQUIRED_FIELDS, self.OPTIONAL_FIELDS)
      if result is not None:
        ret.append(result)
    return ret
