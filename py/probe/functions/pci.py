# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import sysfs
from cros.factory.probe.functions import file as file_module
from cros.factory.utils.arg_utils import Arg


def ReadPCISysfs(path):
  logging.debug('Read PCI path: %s', path)
  ret = sysfs.ReadSysfs(path, ['vendor', 'device'])
  if ret is None:
    return None

  # Add PCI 'revision_id' field.
  pci_revision_id_offset = 0x08
  file_path = os.path.join(path, 'config')
  content = file_module.ReadFile(file_path, binary_mode=True,
                                 skip=pci_revision_id_offset, size=1)
  if content is None:
    return None
  ret['revision_id'] = content
  return ret


class PCIFunction(function.ProbeFunction):
  """Reads the PCI sysfs structure.

  Each result should contain these fields:
    vendor
    device
    revision_id
  """

  ARGS = [
      Arg('dir_path', str, 'The path of target sysfs folder.'),
  ]

  def Probe(self):
    ret = []
    for path in glob.glob(self.args.dir_path):
      result = ReadPCISysfs(path)
      if result is not None:
        ret.append(result)
    return ret
