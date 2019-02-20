# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


KNOWN_CPU_TYPES = type_utils.Enum(['x86', 'arm'])


class GenericCPUFunction(cached_probe_function.LazyCachedProbeFunction):
  """Probe the generic CPU information."""

  ARGS = [
      Arg('cpu_type', str, 'The type of CPU. "x86" or "arm".', default=None),
  ]

  def GetCategoryFromArgs(self):
    if self.args.cpu_type is None:
      logging.info('cpu_type is not assigned. Determine by crossystem.')
      self.args.cpu_type = process_utils.CheckOutput(
          'crossystem arch', shell=True)

    if self.args.cpu_type not in KNOWN_CPU_TYPES:
      raise cached_probe_function.InvalidCategoryError(
          'cpu_type should be one of %r.', list(KNOWN_CPU_TYPES))

    return self.args.cpu_type

  @classmethod
  def ProbeDevices(cls, category):
    if category == KNOWN_CPU_TYPES.x86:
      return cls._ProbeX86()
    if category == KNOWN_CPU_TYPES.arm:
      return cls._ProbeArm()
    return function.NOTHING

  @classmethod
  def _ProbeX86(cls):
    cmd = r'sed -nr "s/^model name\s*: (.*)/\1/p" /proc/cpuinfo'
    try:
      stdout = process_utils.CheckOutput(cmd, shell=True, log=True).splitlines()
    except subprocess.CalledProcessError:
      return function.NOTHING
    return {
        'model': stdout[0].strip(),
        'cores': str(len(stdout))}

  @classmethod
  def _ProbeArm(cls):
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

    return {
        'model': model.strip(),
        'cores': cores.strip(),
        'hardware': hardware.strip()}
