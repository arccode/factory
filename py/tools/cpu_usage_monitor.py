#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils import log_utils


class CPUUsageMonitor(object):
  # Lines of header from 'top'.
  HEADER_LINES = 6
  # Maximum number of characters reported for a command.
  COMMAND_LENGTH = 64
  # Maximum number of processes reported.
  NUM_TOP_PROCESSES = 3
  # Only reports processes with CPU usage exceeding this threshold.
  CPU_THRESHOLD = 10

  def __init__(self, period_secs, dut):
    self._period_secs = period_secs
    self.dut = dut

  def _GetLoadString(self):
    return ', '.join('%.1f' % load for load in self.dut.status.load_avg)

  def GetStatus(self):
    """Get the current CPU usage status.

    Returns:
      A string of current CPU usage.
    """
    msg = []
    msg.append('Load average: %s' % self._GetLoadString())

    # Get column legend from 'top' and throw away summary header and legend
    top_output = self.dut.CheckOutput(
        ['top', '-b', '-c', '-n', '1', '-w', '512']).splitlines()
    column_ids = top_output[self.HEADER_LINES].split()
    pid_column = column_ids.index('PID')
    cpu_column = column_ids.index('%CPU')
    command_column = column_ids.index('COMMAND')
    top_output = top_output[self.HEADER_LINES + 1:]

    # Find up to NUM_TOP_PROCESSES processes with CPU usage >= CPU_THRESHOLD
    for process in top_output[0:self.NUM_TOP_PROCESSES]:
      attr = process.split(None, command_column)
      if float(attr[cpu_column]) < self.CPU_THRESHOLD:
        break
      command = attr[command_column][0:self.COMMAND_LENGTH]
      msg.append('Process %s using %s%% CPU: %s' %
                 (attr[pid_column], attr[cpu_column], command))

    return '; '.join(msg)

  def Check(self):
    """Checks the current CPU usage status.

    Logs current load average and top three processes that use more than 10%
    CPU.
    """
    try:
      msg = self.GetStatus()
    except Exception:
      logging.exception('Unable to check CPU usage')
    else:
      logging.info(msg)

  def CheckForever(self):
    while True:
      self.Check()
      time.sleep(self._period_secs)


def main():
  parser = argparse.ArgumentParser(description='Monitor CPU usage')
  parser.add_argument('--period_secs', '-p', help='Interval between checks',
                      type=int, required=False, default=120)
  args = parser.parse_args()
  log_utils.InitLogging()

  monitor = CPUUsageMonitor(args.period_secs, device_utils.CreateDUTInterface())
  monitor.CheckForever()

if __name__ == '__main__':
  main()
