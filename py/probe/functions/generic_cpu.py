# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils import process_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


KNOWN_CPU_TYPES = type_utils.Enum(['x86', 'arm'])


class GenericCPUFunction(function.ProbeFunction):
  """Probe the generic CPU information.

  The function is ported from `py/gooftool/probe.py` module.
  """

  ARGS = [
      Arg('cpu_type', str, 'The type of CPU. "x86" or "arm".', default=None),
  ]

  def Probe(self):
    if self.args.cpu_type is None:
      logging.info('cpu_type is not assigned. Determine by crossystem.')
      self.args.cpu_type = process_utils.CheckOutput(
          'crossystem arch', shell=True)
    if self.args.cpu_type not in KNOWN_CPU_TYPES:
      logging.error('cpu_type should be one of %r.', list(KNOWN_CPU_TYPES))
      return function.NOTHING

    if self.args.cpu_type == KNOWN_CPU_TYPES.x86:
      return self._ProbeX86()
    if self.args.cpu_type == KNOWN_CPU_TYPES.arm:
      return self._ProbeArm()

  def _ProbeX86(self):
    cmd = r'sed -nr "s/^model name\s*: (.*)/\1/p" /proc/cpuinfo'
    try:
      stdout = process_utils.CheckOutput(cmd, shell=True, log=True).splitlines()
    except subprocess.CalledProcessError:
      return function.NOTHING
    return {
        'model': stdout[0].strip(),
        'cores': str(len(stdout))}

  def _ProbeArm(self):
    # For platforms like arm, it sometimes gives the model name in 'Processor',
    # and sometimes in 'model name'. But they all give something like 'ARMv7
    # Processor rev 4 (v71)' only. So to uniquely identify an ARM CPU, we should
    # use the 'Hardware' field.
    CPU_INFO_FILE = '/proc/cpuinfo'
    with open(CPU_INFO_FILE, 'r') as f:
      cpuinfo = f.read()

    def _SearchCPUInfo(regex, name):
      matched = re.search(regex, cpuinfo, re.MULTILINE)
      if matched is None:
        logging.error('Unable to find "%s" field in %s.', name, CPU_INFO_FILE)
        return 'unknown'
      return matched.group(1)

    model = _SearchCPUInfo(r'^(?:Processor|model name)\s*: (.*)$', 'model')
    hardware = _SearchCPUInfo(r'^Hardware\s*: (.*)$', 'hardware')
    cores = process_utils.CheckOutput('nproc', shell=True, log=True)
    return {
        'model': model.strip(),
        'cores': cores.strip(),
        'hardware': hardware.strip()}
