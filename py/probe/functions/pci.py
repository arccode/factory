# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os

from cros.factory.probe.functions import file as file_module
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


def ReadPCISysfs(path):
  logging.debug('Read PCI path: %s', path)
  ret = sysfs.ReadSysfs(path, ['class', 'vendor', 'device'],
                        ['subsystem_device'])
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
  """Probes all PCI devices listed in the sysfs ``/sys/bus/pci/devices/``.

  Description
  -----------
  This function goes through ``/sys/bus/pci/devices/`` to read attributes of
  each PCI device listed there.  Each result should contain these fields:

  - ``device_path``: Pathname of the sysfs directory.
  - ``class``
  - ``vendor``
  - ``device``
  - ``revision_id``

  Examples
  --------
  Let's say the Chromebook has two PCI devices.  One of which
  (at ``/sys/bus/pci/devices/0000:00:00.1``) has the attributes:

  - ``class=0x010203``
  - ``vendor=0x0123``
  - ``device=0x4567``
  - ``revision_id=01``

  And the other one (at ``/sys/bus/pci/devices/0000:00:01.1``) has the
  attributes:

  - ``class=0x020406``
  - ``vendor=0x0246``
  - ``device=0x1357``
  - ``revision_id=01``

  Then the probe statement::

    {
      "eval": "pci"
    }

  will have the corresponding probed result::

    [
      {
        "bus_type": "pci",
        "class": "0x010203",
        "vendor": "0x0123",
        "device": "0x4567",
        "revision_id": "0x01"
      },
      {
        "bus_type": "pci",
        "class": "0x020406",
        "vendor": "0x0246",
        "device": "0x1357",
        "revision_id": "0x01"
      }
    ]

  To verify if the Chromebook has the PCI device which ``vendor`` is ``0x0246``,
  you can write a probe statement like::

    {
      "eval": "pci",
      "expect": {
        "vendor": "0x0246"
      }
    }

  The corresponding probed result will be empty if and only if there's no
  PCI device which ``vendor`` is ``0x0246`` found.

  Another use case is that you can ask this function to parse a specific
  PCI device sysfs directly like ::

    {
      "eval" "pci:/sys/bus/pci/devices/0000:00:01.1"
    }
  """

  GLOB_PATH = '/sys/bus/pci/devices/*'

  @classmethod
  def ProbeDevice(cls, dir_path):
    return ReadPCISysfs(dir_path)
