# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.utils.cpufreq_manager import CpufreqManager
from cros.factory.utils import type_utils


class CPUFreqManager(plugin.Plugin):

  def __init__(self, goofy):
    super(CPUFreqManager, self).__init__(goofy, [plugin.RESOURCE.CPU])
    self._cpu_freq_manager = CpufreqManager(event_log=goofy.event_log)

  @type_utils.Overrides
  def OnStart(self):
    self._cpu_freq_manager.SetEnabled(True)

  @type_utils.Overrides
  def OnStop(self):
    self._cpu_freq_manager.SetEnabled(False)

  @type_utils.Overrides
  def OnDestroy(self):
    self._cpu_freq_manager.Stop()
