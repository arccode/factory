# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs


class GenericBatteryFunction(sysfs.SysfsFunction):
  """Probe the generic battery information.

  The function is ported from `py/gooftool/probe.py` module.
  """

  ARGS = []

  def __init__(self, **kwargs):
    super(GenericBatteryFunction, self).__init__(**kwargs)

    self.args.dir_path = '/sys/class/power_supply/*'
    self.args.keys = ['manufacturer', 'model_name', 'technology', 'type']
    self.args.optional_keys = ['charge_full_design', 'energy_full_design']

  def Probe(self):
    def ValidBatteryResult(result):
      return result.pop('type') == 'Battery' and (
          'charge_full_design' in result or 'energy_full_design' in result)

    return [result for result in super(GenericBatteryFunction, self).Probe()
            if ValidBatteryResult(result)]
