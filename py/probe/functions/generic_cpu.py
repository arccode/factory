# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


KNOWN_CPU_TYPES = type_utils.Enum(['x86', 'arm'])


class GenericCPUFunction(probe_function.ProbeFunction):
  """Probe the generic CPU information."""

  ARGS = [
      Arg('cpu_type', str,
          'The type of CPU. "x86" or "arm". Default: Auto detection.',
          default=None),
  ]

  def __init__(self, **kwargs):
    super(GenericCPUFunction, self).__init__(**kwargs)

    if self.args.cpu_type is None:
      logging.info('cpu_type not specified. Determine by crossystem.')
      self.args.cpu_type = process_utils.CheckOutput(
          'crossystem arch', shell=True)
    if self.args.cpu_type not in KNOWN_CPU_TYPES:
      raise ValueError('cpu_type should be one of %r.' % list(KNOWN_CPU_TYPES))

  def Probe(self):
    if self.args.cpu_type == KNOWN_CPU_TYPES.x86:
      return self._ProbeX86()
    return self._ProbeArm()

  @staticmethod
  def _ProbeX86():
    cmd = r'/usr/bin/lscpu'
    try:
      stdout = process_utils.CheckOutput(cmd, shell=True, log=True)
    except subprocess.CalledProcessError:
      return function.NOTHING

    def _CountCores(cpu_list):
      count = 0
      for cpu in cpu_list.split(','):
        if '-' in cpu:
          # e.g. 3-5 ==> core 3, 4, 5 are enabled
          l, r = map(int, cpu.split('-'))
          count += r - l + 1
        else:
          # e.g. 12 ==> core 12 is enabled
          count += 1
      return count

    def _ReSearch(regex):
      return re.search(regex, stdout).group(1).strip()

    model = _ReSearch(r'Model name:(.*)')
    physical = int(_ReSearch(r'CPU\(s\):(.*)'))
    online = _CountCores(_ReSearch(r'On-line.*:(.*)'))
    return {
        'model': model,
        'cores': str(physical),
        'online_cores': str(online)}

  @staticmethod
  def _ProbeArm():
    # For ARM platform, ChromeOS kernel has/had special code to expose fields
    # like 'model name' or 'Processor' and 'Hardware' field.  However, this
    # doesn't seem to be available in ARMv8 (and probably all future versions).
    # In this case, we will use 'CPU architecture' to identify the ARM version.

    CPU_INFO_FILE = '/proc/cpuinfo'
    with open(CPU_INFO_FILE, 'r') as f:
      cpuinfo = f.read()

    def _SearchCPUInfo(regex, name):
      matched = re.search(regex, cpuinfo, re.MULTILINE)
      if matched is None:
        logging.warning('Unable to find "%s" field in %s.', name, CPU_INFO_FILE)
        return 'unknown'
      return matched.group(1)

    # For ARMv7, model and hardware should be available.
    model = _SearchCPUInfo(r'^(?:Processor|model name)\s*: (.*)$', 'model')
    hardware = _SearchCPUInfo(r'^Hardware\s*: (.*)$', 'hardware')

    # For ARMv8, there is no model nor hardware, we use 'CPU architecture' as
    # backup plan.  For an ARM device project (reference board and all follower
    # devices), all SKUs should be using same ARM CPU.  So we don't really need
    # detail information.  In the future, we can consider adding other "CPU .*"
    # fields into model name if we think they are important.
    architecture = _SearchCPUInfo(r'^CPU architecture\s*: (\d+)$',
                                  'architecture')
    if model.strip() == 'unknown' and architecture != 'unknown':
      model = 'ARMv' + architecture.strip()
    else:
      logging.error('Unable to construct "model" of ARM CPU')

    cores = process_utils.CheckOutput('nproc', shell=True, log=True)
    # TODO(frankbozar): count the number of online cores

    return {
        'model': model.strip(),
        'cores': cores.strip(),
        'hardware': hardware.strip()}
