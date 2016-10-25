# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import paths
from cros.factory.utils import process_utils


class ThermalMonitor(plugin.Plugin):
  """Dump thermal information of the device with at the given interval."""

  def __init__(self, goofy, period_secs, delta_threshold):
    """Constructor

    Args:
      period_secs: dump thermal data at the given interval.
      delta_threshold: dump thermal data only if a value greater than
          delta observed.
    """
    super(ThermalMonitor, self).__init__(goofy)
    self._period_secs = period_secs
    self._delta_threshold = delta_threshold
    self._thermal_watcher = None

  def OnStart(self):
    self._thermal_watcher = process_utils.Spawn(
        ['py/tools/thermal_monitor.py',
         '-p', str(self._period_secs),
         '-d', str(self._delta_threshold)],
        cwd=paths.FACTORY_PATH)

  def OnStop(self):
    self._thermal_watch.terminate()
