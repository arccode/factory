# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import file as file_module
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


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
  ret['bus_type'] = 'pci'
  return ret


class PCIFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Reads the PCI sysfs structure.

  Each result should contain these fields:
    vendor
    device
    revision_id
  """

  GLOB_PATH = '/sys/bus/pci/devices/*'

  @classmethod
  def ProbeDevice(cls, dir_path):
    return ReadPCISysfs(dir_path)
