# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import paths
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class CPUUsageMonitor(plugin.Plugin):

  def __init__(self, goofy, period_secs):
    super(CPUUsageMonitor, self).__init__(goofy)
    self._period_secs = period_secs
    self._cpu_usage_monitor = None

  @type_utils.Overrides
  def OnStart(self):
    self._cpu_usage_monitor = process_utils.Spawn(
        ['py/tools/cpu_usage_monitor.py', '-p', str(self._period_secs)],
        cwd=paths.FACTORY_DIR)

  @type_utils.Overrides
  def OnStop(self):
    if self._cpu_usage_monitor:
      self._cpu_usage_monitor.terminate()
