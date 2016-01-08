#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility functions that are useful to factory tests."""

import os
import re
import sys
import traceback

import factory_common  # pylint: disable=W0611
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


def IsFreon(dut=None):
  """Checks if the board is running freon.

  Returns:
    True if the board is running freon; False otherwise.
  """
  # Currently we only enable frecon on freon boards. We might need to revisit
  # this in the future to find a more deterministic way to probe freon board.
  return (os.path.exists('/sbin/frecon') if dut else
          dut.Call('[ -e /sbin/frecon ]') == 0)


def in_qemu():
  """Returns True if running within QEMU."""
  return 'QEMU' in open('/proc/cpuinfo').read()


def in_cros_device():
  """Returns True if running on a Chrome OS device."""
  if not os.path.exists('/etc/lsb-release'):
    return False
  with open('/etc/lsb-release') as f:
    lsb_release = f.read()
  return re.match(r'^CHROMEOS_RELEASE', lsb_release, re.MULTILINE) is not None


def var_log_messages_before_reboot(lines=100,
                                   max_length=5 * 1024 * 1024,
                                   path='/var/log/messages'):
  """Returns the last few lines in /var/log/messages before the current boot.

  Args:
    lines: number of lines to return.
    max_length: maximum amount of data at end of file to read.
    path: path to /var/log/messages.

  Returns:
    An array of lines. Empty if the marker indicating kernel boot
    could not be found.
  """
  offset = max(0, os.path.getsize(path) - max_length)
  with open(path) as f:
    f.seek(offset)
    data = f.read()

  # Find the last element matching the RE signaling kernel start.
  matches = list(re.finditer(
      r'^(\S+)\s.*kernel:\s+\[\s+0\.\d+\] Linux version', data, re.MULTILINE))
  if not matches:
    return []

  match = matches[-1]
  tail_lines = data[:match.start()].split('\n')
  tail_lines.pop()  # Remove incomplete line at end

  # Skip some common lines that may have been written before the Linux
  # version.
  while tail_lines and any(
      re.search(x, tail_lines[-1])
      for x in [r'0\.000000\]',
                r'rsyslogd.+\(re\)start',
                r'/proc/kmsg started']):
    tail_lines.pop()

  # Done! Return the last few lines.
  return tail_lines[-lines:] + [
      '<after reboot, kernel came up at %s>' % match.group(1)]


def FormatExceptionOnly():
  """Formats the current exception string.

  Must only be called from inside an exception handler.

  Returns:
    A string.
  """
  return '\n'.join(
      traceback.format_exception_only(*sys.exc_info()[:2])).strip()


def ResetCommitTime():
  """Remounts partitions with commit=0.

  The standard value on CrOS (commit=600) is likely to result in
  corruption during factory testing.  Using commit=0 reverts to the
  default value (generally 5 s).
  """
  if sys_utils.in_chroot():
    return

  devices = set()
  with open('/etc/mtab', 'r') as f:
    for line in f.readlines():
      cols = line.split(' ')
      device = cols[0]
      options = cols[3]
      if 'commit=' in options:
        devices.add(device)

  # Remount all devices in parallel, and wait.  Ignore errors.
  for process in [
      process_utils.Spawn(['mount', p, '-o', 'commit=0,remount'], log=True)
      for p in sorted(devices)]:
    process.wait()
