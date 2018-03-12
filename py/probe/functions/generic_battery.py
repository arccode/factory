# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


class GenericBatteryFunction(
    cached_probe_function.GlobPathCachedProbeFunction):

  GLOB_PATH = '/sys/class/power_supply/*'
  ARGS = []

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeDevice(cls, dir_path):
    result = sysfs.ReadSysfs(
        dir_path, ['manufacturer', 'model_name', 'technology', 'type'],
        optional_keys=['charge_full_design', 'energy_full_design'])
    if result is not None and result.pop('type') == 'Battery' and (
        'charge_full_design' in result or 'energy_full_design' in result):
      return result
