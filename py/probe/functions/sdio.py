# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


REQUIRED_FIELDS = ['vendor']
OPTIONAL_FIELDS = ['manufacturer', 'product', 'bcdDevice']


def ReadSDIOSysfs(dir_path):
  ret = sysfs.ReadSysfs(dir_path, ['vendor', 'device'])
  if ret is None:
    return None

  ret['bus_type'] = 'sdio'
  return ret


class SDIOFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Probes all SDIO devices listed in the sysfs ``/sys/bus/sdio/devices/``.

  Description
  -----------
  This function goes through ``/sys/bus/sdio/devices/`` to read attributes of
  each SDIO device listed there.  Each result should contain these fields:

  - ``device_path``: Pathname of the sysfs directory.
  - ``vendor``
  - ``device``

  Examples
  --------
  Let's say the Chromebook has two SDIO devices.  One of which
  (at ``/sys/bus/sdio/devices/mmc1:0001:1``) has the attributes:

  - ``vendor=0x0123``
  - ``device=0x4567``

  And the other one (at ``/sys/bus/sdio/devices/mmc1:0002:1``) has the
  attributes:

  - ``vendor=0x0246``
  - ``device=0x1357``


  Then the probe statement::

    {
      "eval": "sdio"
    }

  will have the corresponding probed result::

    [
      {
        "bus_type": "sdio",
        "vendor": "0123",
        "device": "4567"
      },
      {
        "bus_type": "sdio",
        "vendor": "0246",
        "device": "1357"
      }
    ]

  To verify if the Chromebook has SDIO device which ``vendor`` is ``0x0246``,
  you can write a probe statement like::

    {
      "eval": "sdio",
      "expect": {
        "vendor": "0246"
      }
    }

  The corresponding probed result will be empty if and only if there's no
  SDIO device which ``vendor`` is ``0x0246`` found.

  """

  GLOB_PATH = '/sys/bus/sdio/devices/*'

  @classmethod
  def ProbeDevice(cls, dir_path):
    return ReadSDIOSysfs(dir_path)
