# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import sysfs
from cros.factory.utils.arg_utils import Arg


_REQUIRED_FIELDS = ['idVendor', 'idProduct']
_OPTIONAL_FIELDS = ['manufacturer', 'product', 'bcdDevice']


def ReadUSBSysfs(path):
  logging.debug('Read USB path: %s', path)
  # Read required fields.
  ret = sysfs.ReadSysfs(path, _REQUIRED_FIELDS)
  if not ret:
    return None

  # Read optional fields.
  for key in _OPTIONAL_FIELDS:
    result = sysfs.ReadSysfs(path, [key])
    if result is not None:
      ret.update(result)
  return ret


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
      Arg('dir_path', str, 'The path of target sysfs folder.'),
  ]


  def Probe(self):
    ret = []
    for path in glob.glob(self.args.dir_path):
      result = ReadUSBSysfs(path)
      if result is not None:
        ret.append(result)
    return ret

