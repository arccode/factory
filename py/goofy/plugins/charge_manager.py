# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from cros.factory.goofy.plugins import periodic_plugin
from cros.factory.goofy.plugins import plugin
from cros.factory.test.utils import charge_manager
from cros.factory.utils import type_utils


class ChargeManager(periodic_plugin.PeriodicPlugin):

  def __init__(self, goofy, period_secs, min_charge_pct, max_charge_pct):
    super(ChargeManager, self).__init__(
        goofy, period_secs, [plugin.RESOURCE.POWER])
    self._charge_manager = charge_manager.ChargeManager(min_charge_pct,
                                                        max_charge_pct)

  @type_utils.Overrides
  def RunTask(self):
    self._charge_manager.AdjustChargeState()

  @type_utils.Overrides
  def OnStop(self):
    super(ChargeManager, self).OnStop()
    self._charge_manager.StartCharging()
