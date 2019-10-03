# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import paths
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class ThermalMonitor(plugin.Plugin):
  """Dump thermal information of the device with at the given interval."""

  def __init__(self, goofy, period_secs, delta_threshold, use_testlog=True):
    """Constructor

    Args:
      period_secs: dump thermal data at the given interval.
      delta_threshold: dump thermal data only if a value greater than
          delta observed.
      use_testlog: use testlog to log thermal data.
    """
    super(ThermalMonitor, self).__init__(goofy)
    self._period_secs = period_secs
    self._delta_threshold = delta_threshold
    self._thermal_watcher = None
    self._use_testlog = use_testlog

  @type_utils.Overrides
  def OnStart(self):
    cmd = ['py/tools/thermal_monitor.py',
           '-p', str(self._period_secs),
           '-d', str(self._delta_threshold)]
    if self._use_testlog:
      cmd.append('-t')

    self._thermal_watcher = process_utils.Spawn(
        cmd, cwd=paths.FACTORY_DIR)

  @type_utils.Overrides
  def OnStop(self):
    self._thermal_watcher.terminate()
