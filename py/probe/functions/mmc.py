# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


REQUIRED_FIELDS = ['cid', 'csd', 'fwrev', 'hwrev', 'manfid', 'oemid']
OPTIONAL_FIELDS = ['name', 'serial']


def ReadMMCSysfs(dir_path):
  result = sysfs.ReadSysfs(
      dir_path, REQUIRED_FIELDS, optional_keys=OPTIONAL_FIELDS)

  if result:
    result['bus_type'] = 'mmc'

  return result


class MMCFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Reads the MMC sysfs structure.

  Each result should contain these fields:
    cid
    csd
    fwrev
    hwrev
    manfid
    oemid
  The result might also contain these optional fields:
    name
    serial
  """

  GLOB_PATH = '/sys/bus/mmc/devices/*'

  @classmethod
  def ProbeDevice(cls, dir_path):
    return ReadMMCSysfs(dir_path)
