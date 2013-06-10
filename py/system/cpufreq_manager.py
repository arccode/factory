# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import service_manager
from cros.factory.utils.file_utils import WriteFile

THERMAL_SERVICE = 'thermal'

class CpufreqManager(object):
  """Manager for CrOS-specific services that mess with cpufreq.

  If disabled, we disable CrOS-specific cpufreq management (i.e., the
  "thermal" service) and lock down the CPU speed.

  Properties:
    enabled: Whether cpufreq services are currently enabled
        (or None if unknown).
    cpufreq_path: Path to the cpufreq directory.
    cpu_speed: CPU speed when cpufreq services are disabled.  This
        defaults (very arbitrarily) to 1.3 GHz but may be modified by
        board-specific hooks.
  """
  enabled = None
  cpufreq_path = '/sys/devices/system/cpu/cpu0/cpufreq'
  cpu_speed_hz = 1300000

  def Stop(self):
    """Stops the cpufreq manager.

    This simply returns cpufreq handling to the default state (enabled).
    """
    self.SetEnabled(True)

  def SetEnabled(self, enabled):
    """Sets whether CrOS-specific cpufreq scaling services are enabled."""
    if self.enabled == enabled:
      return

    logging.info('%s cpufreq services',
                 'Enabling' if enabled else 'Disabling')

    new_status = (service_manager.Status.START if enabled
                  else service_manager.Status.STOP)
    if service_manager.GetServiceStatus(THERMAL_SERVICE) != new_status:
      service_manager.SetServiceStatus(THERMAL_SERVICE, new_status)

    WriteFile(os.path.join(self.cpufreq_path, 'scaling_governor'),
              'interactive' if enabled else 'userspace', log=True)
    if not enabled:
      WriteFile(os.path.join(self.cpufreq_path, 'scaling_setspeed'),
                self.cpu_speed_hz, log=True)

    self.enabled = enabled
