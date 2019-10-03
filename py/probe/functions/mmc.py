# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


REQUIRED_FIELDS = ['cid', 'csd', 'manfid', 'oemid', 'name', 'serial']
OPTIONAL_FIELDS = ['fwrev', 'hwrev']


def ReadMMCSysfs(dir_path):
  result = sysfs.ReadSysfs(
      dir_path, REQUIRED_FIELDS, optional_keys=OPTIONAL_FIELDS)

  if result:
    result['bus_type'] = 'mmc'

  return result


class MMCFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Probes all eMMC devices listed in the sysfs ``/sys/bus/mmc/devices/``.

  Description
  -----------
  This function goes through ``/sys/bus/mmc/devices/`` to read attributes of
  each eMMC device listed there.  Each result should contain these fields:

  - ``device_path``: Pathname of the sysfs directory.
  - ``cid``: Card Identification Register.
  - ``csd``: Card Specific Data Register.
  - ``manfid``: Manufacturer ID (from CID Register).
  - ``name``: Product Name (from CID Register).
  - ``oemid``: OEM/Application ID (from CID Register).
  - ``serial``: Product Serial Number (from CID Register).

  The result might also contain these optional fields if they are exported in
  the sysfs entry:

  - ``fwrev``: Firmware/Product Revision (from CID Register, SD and MMCv1 only).
  - ``hwrev``: Hardware/Product Revision (from CID Register, SD and MMCv1 only).

  Please reference the kernel
  `document <https://www.kernel.org/doc/Documentation/mmc/mmc-dev-attrs.txt>`_
  for more information.

  Examples
  --------
  Let's say the Chromebook has two eMMC devices.  One of which
  (at ``/sys/bus/mmc/devices/mmc0:0001``) has the attributes:

  - ``cid=123412341234``
  - \\.\\.\\.

  And the other one (at ``/sys/bus/mmc/devices/mmc1:0001``) has the
  attributes:

  - ``cid=246824682468``
  - \\.\\.\\.

  Then the probe statement::

    {
      "eval": "mmc"
    }

  will have the corresponding probed result::

    [
      {
        "bus_type": "mmc",
        "cid": "123412341234",
        ...
      },
      {
        "bus_type": "mmc",
        "cid": "246824682468",
        ...
      }
    ]

  To verify if the Chromebook has the eMMC device which ``cid`` is
  ``123412341234``, you can write a probe statement like::

    {
      "eval": "mmc",
      "expect": {
        "cid": "123412341234"
      }
    }

  The corresponding probed result will be empty if and only if there's no
  eMMC device which ``cid`` is ``123412341234`` found.

  Another use case is that you can ask this function to parse a specific
  eMMC device sysfs directly like ::

    {
      "eval" "mmc:/sys/bus/mmc/devices/mmc1:0001"
    }
  """

  GLOB_PATH = '/sys/bus/mmc/devices/*'

  @classmethod
  def ProbeDevice(cls, dir_path):
    return ReadMMCSysfs(dir_path)
