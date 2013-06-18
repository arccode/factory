# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import traceback

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import service_manager
from cros.factory.utils.file_utils import WriteFile

THERMAL_SERVICE = 'thermal'
RETRY_COUNT = 3

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
    event_log: If set, an event log object to use to log changes to enablement.
  """
  enabled = None
  cpufreq_path = '/sys/devices/system/cpu/cpu0/cpufreq'
  cpu_speed_hz = 1300000

  def __init__(self, event_log=None):
    self.event_log = event_log

  def Stop(self):
    """Stops the cpufreq manager.

    This simply returns cpufreq handling to the default state (enabled).
    """
    self.SetEnabled(True)

  def SetEnabled(self, enabled):
    """Sets whether CrOS-specific cpufreq scaling services are enabled."""
    if self.enabled == enabled:
      return

    # Retry several times, since as per tbroch, writing to scaling_*
    # may be flaky.
    for retry_count in range(RETRY_COUNT):
      thermal_service_status = (service_manager.Status.START if enabled
                                else service_manager.Status.STOP)
      governor = 'interactive' if enabled else 'userspace'
      cpu_speed_hz = None if enabled else self.cpu_speed_hz

      logging.info('cpufreq: setting thermal_service_status=%s, governor=%s, '
                   'cpu_speed_hz=%s, retry_count=%d',
                   thermal_service_status, governor, cpu_speed_hz, retry_count)

      if (service_manager.GetServiceStatus(THERMAL_SERVICE) !=
          thermal_service_status):
        service_manager.SetServiceStatus(THERMAL_SERVICE,
                                         thermal_service_status)

      success = False
      exception = None
      try:
        WriteFile(os.path.join(self.cpufreq_path, 'scaling_governor'),
                  governor, log=True)
        if not enabled:
          WriteFile(os.path.join(self.cpufreq_path, 'scaling_setspeed'),
                    self.cpu_speed_hz, log=True)
        success = True
      except:  # pylint: disable=W0702
        logging.exception('Unable to set CPU scaling parameters')
        exception = traceback.format_exc()

      if self.event_log:
        self.event_log.Log(
            'set_cpu_speed',
            thermal_service_status=thermal_service_status,
            cpu_speed_hz=cpu_speed_hz,
            governor=governor,
            success=success,
            exception=exception,
            retry_count=retry_count)

      if success:
        break

    if success:
      self.enabled = enabled
    else:
      logging.warn('Gave up on trying to set CPU scaling parameters')
