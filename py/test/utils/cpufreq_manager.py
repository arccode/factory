# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import subprocess
import traceback

from cros.factory.utils import file_utils
from cros.factory.utils import service_utils


_RETRY_COUNT = 3

CPUX_CPUFREQ_PATH = '/sys/devices/system/cpu/cpu%d/cpufreq'
"""Path to the cpufreq directory of the Xth CPU."""

CPU_ONLINE_PATH = '/sys/devices/system/cpu/online'
"""Path to the list of online CPUs."""


class CpufreqManager:
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

  cpu_speed_hz = None
  """CPU speed when cpufreq services are disabled if not None, but this is not
  supported by most CPUs today.
  """

  index_to_freq_settings = None
  """Store the CPU frequency settings of each core. This is used to restore the
  original CPU frequency settings, since some factory tests modify them.
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
    for retry_count in range(_RETRY_COUNT):
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
          path = CPUX_CPUFREQ_PATH % index
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
      logging.warning('Gave up on trying to set CPU scaling parameters')

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

    The content in CPU_ONLINE_PATH is in linux bitmap output format %*pbl.
    For example, 0x0779 in that format is "0,3-6,8-10".
    """
    online_string = file_utils.ReadFile(CPU_ONLINE_PATH)
    online_list = []
    for matched in re.finditer(r'(\d+)(?:-(\d+))?(?:,|$)', online_string):
      lower_bound = int(matched.group(1))
      upper_bound = int(matched.group(2)) if matched.group(2) else lower_bound
      online_list += list(range(lower_bound, upper_bound+1))
    return online_list

  def _IsFreqValid(self, core, freq_key, freq_to_set):
    if freq_to_set is None:
      return False

    cpufreq_path = CPUX_CPUFREQ_PATH % core
    scaling_freq_path = os.path.join(cpufreq_path, freq_key)
    cpuinfo_max_freq_path = os.path.join(cpufreq_path, 'cpuinfo_max_freq')
    cpuinfo_min_freq_path = os.path.join(cpufreq_path, 'cpuinfo_min_freq')

    for times_tried in range(_RETRY_COUNT):
      try:
        highest_freq = int(file_utils.ReadFile(cpuinfo_max_freq_path).strip())
        lowest_freq = int(file_utils.ReadFile(cpuinfo_min_freq_path).strip())
        break
      except Exception:
        logging.exception('Unable to read: %s and %s.', cpuinfo_max_freq_path,
                          cpuinfo_min_freq_path)
        if times_tried == _RETRY_COUNT - 1:
          logging.warning('Exceed maximum retries. Give up reading %s and %s.',
                          cpuinfo_max_freq_path, cpuinfo_min_freq_path)
          return False

    if lowest_freq > freq_to_set or freq_to_set > highest_freq:
      logging.error(
          'Try to set %s to %d, but found value out of bound.\n'
          'Expect to be between %d and %d.', scaling_freq_path, freq_to_set,
          highest_freq, lowest_freq)
      return False

    return True

  def _TrySetCpufreq(self, core, freq_key, freq_to_set):
    """Try to set the scaling frequency and check if the value is valid."""
    if freq_to_set is None:
      return

    cpufreq_path = CPUX_CPUFREQ_PATH % core
    scaling_path = os.path.join(cpufreq_path, freq_key)

    for _ in range(_RETRY_COUNT):
      try:
        old_value = file_utils.ReadFile(scaling_path).strip()
        file_utils.WriteFile(scaling_path, freq_to_set)
      except Exception:
        logging.exception('Fail to set the content of file %s to %s.',
                          scaling_path, freq_to_set)
      else:
        self.index_to_freq_settings[core][freq_key] = old_value
        logging.info(
            'Original value in file %s is %s,'
            ' and the new value is %s.', scaling_path, old_value, freq_to_set)
        break
    else:
      logging.warning('Exceed maximum retries. Give up setting %s.',
                      scaling_path)

  def SetFrequency(self, cpufreq_to_value: dict):
    """Set the CPU frequency to specific value.

    Args:
      cpufreq_to_value: a dict which contains three key/value pairs, including:
                        scaling_min_freq, scaling_max_freq and scaling_governor
    """
    max_freq_key = 'scaling_max_freq'
    min_freq_key = 'scaling_min_freq'
    governor_key = 'scaling_governor'

    self.index_to_freq_settings = {}
    for core in self._GetOnlineCPUs():
      self.index_to_freq_settings[core] = {}

      if self._IsFreqValid(core, max_freq_key, cpufreq_to_value[max_freq_key]):
        self._TrySetCpufreq(core, max_freq_key, cpufreq_to_value[max_freq_key])

      if self._IsFreqValid(core, min_freq_key, cpufreq_to_value[min_freq_key]):
        self._TrySetCpufreq(core, min_freq_key, cpufreq_to_value[min_freq_key])

      self._TrySetCpufreq(core, governor_key, cpufreq_to_value[governor_key])

  def RestoreFrequency(self):
    """Restore the original CPU frequency settings of each core."""
    if self.index_to_freq_settings is None:
      logging.info('Cannot restore original cpu frequency settings')
      return

    for core, settings in self.index_to_freq_settings.items():
      cpu_path = CPUX_CPUFREQ_PATH % core
      for item, value in settings.items():
        freq_path = os.path.join(cpu_path, item)
        try:
          file_utils.WriteFile(freq_path, value)
        except Exception:
          logging.warning('Fail to restore the content of %s to %s', freq_path,
                          value)
        else:
          logging.info('Write value %s to file %s', value, freq_path)

    self.index_to_freq_settings = None

  def GetCurrentFrequency(self):
    raw_output = file_utils.ReadFile('/proc/cpuinfo')
    cpu_mhz_pattern = r'^cpu MHz[\t]+: (\d+.\d*)\n'
    processor_pattern = r'^processor[\t]+: (\d+)\n'

    cpufreqs_str = re.findall(cpu_mhz_pattern, raw_output, re.MULTILINE)
    processors_str = re.findall(processor_pattern, raw_output, re.MULTILINE)

    # pylint: disable=map-builtin-not-iterating
    cpufreqs_int = map(float, cpufreqs_str)
    processors_int = map(int, processors_str)

    return [cpufreq for _, cpufreq in sorted(zip(processors_int, cpufreqs_int))]
