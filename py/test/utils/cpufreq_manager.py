# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import subprocess
import traceback

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import service_utils


RETRY_COUNT = 3


class CpufreqManager(object):
  """Manager for CrOS-specific services that mess with cpufreq.

  If disabled, we disable CrOS-specific cpufreq management (i.e., the "thermal"
  service) and lock down the CPU speed. Note some services, for example 'dptf',
  are critical and can't be disabled because the hardware throttling may not
  prevent overheating in time so DUT may shutdown unexpectedly in stress tests.

  Args:
    event_log: If set, an event log object to use to log changes to enablement.
  """
  enabled = None
  """Whether cpufreq services are currently enabled (or None if unknown)."""

  cpuX_cpufreq_path = '/sys/devices/system/cpu/cpu%d/cpufreq'
  """Path to the cpufreq directory of the Xth CPU."""

  cpu_online_path = '/sys/devices/system/cpu/online'
  """Path to the list of online CPUs."""

  cpu_speed_hz = None
  """CPU speed when cpufreq services are disabled if not None, but this is not
  supported by most CPUs today.
  """

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
      thermal_service_status = (service_utils.Status.START if enabled
                                else service_utils.Status.STOP)
      # crbug.com/736746 To really set CPU frequency governor should be
      # 'userspace' but it's not supported by most CPU today so instead we want
      # CPU to run in full speed.
      governor = 'powersave' if enabled else 'performance'
      cpu_speed_hz = None if enabled else self.cpu_speed_hz
      success = True
      exception = None
      try:
        online_CPUs = self._GetOnlineCPUs()
      except Exception:
        online_CPUs = []
        success = False
        logging.exception('Unable to get online CPUs.')
        exception = traceback.format_exc()

      logging.info('cpufreq: setting thermal_service_status=%s, governor=%s, '
                   'cpu_speed_hz=%s, retry_count=%d, online_CPUs=%r.',
                   thermal_service_status, governor, cpu_speed_hz, retry_count,
                   online_CPUs)

      for service in self._GetThermalService():
        try:
          current_service_status = service_utils.GetServiceStatus(service)
        except subprocess.CalledProcessError:
          # These thermal services are kernel and board dependent. Just let it
          # go if we can not find the service.
          pass
        else:
          if current_service_status != thermal_service_status:
            service_utils.SetServiceStatus(service, thermal_service_status)

      for index in online_CPUs:
        try:
          path = self.cpuX_cpufreq_path % index
          file_utils.WriteFile(os.path.join(path, 'scaling_governor'), governor)
          if cpu_speed_hz:
            file_utils.WriteFile(
                os.path.join(path, 'scaling_setspeed'), self.cpu_speed_hz)
        except Exception:
          success = False
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

  def _GetThermalService(self):
    possible_services = ('thermal')

    exist_services = []
    for service in possible_services:
      if service_utils.CheckServiceExists(service):
        exist_services.append(service)

    if not exist_services:
      logging.info('No thermal-control service is available! %s',
                   possible_services)

    if len(exist_services) > 1:
      logging.info('More then one thermal-control service are found: %s',
                   exist_services)

    return exist_services

  def _GetOnlineCPUs(self):
    """Get a list of online CPUs.

    The content in self.cpu_online_path is in linux bitmap output format %*pbl.
    For example, 0x0779 in that format is "0,3-6,8-10".
    """
    online_string = file_utils.ReadFile(self.cpu_online_path)
    online_list = []
    for matched in re.finditer(r'(\d+)(?:-(\d+))?(?:,|$)', online_string):
      lower_bound = int(matched.group(1))
      upper_bound = int(matched.group(2)) if matched.group(2) else lower_bound
      online_list += list(range(lower_bound, upper_bound+1))
    return online_list
