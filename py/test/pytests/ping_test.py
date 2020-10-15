# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Ping connection test.

Description
-----------
Tests network connection by pinging a host for a period of time. Then checks
the percentage of successful pings is above some threshold or not.

If moving_window_size is set, it will check the percentage within the moving
window during the test. It always checks the percentage of successful pings for
the whole duration at the end of the test.

Test Procedure
--------------
This is an automated test without user interaction.

Dependency
----------
The program ``ping``.

Examples
--------
To ping 192.168.0.1 every 2 seconds for 10 seconds, and checks the successful
pings are >= 70% at the end of the test (The default values), add this in test
list::

  {
    "pytest_name": "ping_test",
    "args": {
      "host": "192.168.0.1"
    }
  }

To ping 192.168.0.1 every 10 seconds for 120 seconds, and checks the successful
pings are >= 60% at the end of the test::

  {
    "pytest_name": "ping_test",
    "args": {
      "duration_secs": 120,
      "host": "192.168.0.1",
      "interval_secs": 10,
      "ping_success_percent": 60
    }
  }

To ping 192.168.0.1 on interface eth0 every 10 seconds for 120 seconds, checks
the successful pings are >= 70% within the moving window of 5 pings, and also
checks the successful pings are >= 70% overall::

  {
    "pytest_name": "ping_test",
    "args": {
      "duration_secs": 120,
      "host": "192.168.0.1",
      "interface": "eth0",
      "interval_secs": 10,
      "moving_window_size": 5
    }
  }
"""

import logging

from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import time_utils


class PingTest(test_case.TestCase):
  ARGS = [
      Arg('host', str, 'The IP address or hostname to ping.'),
      Arg('interface', str, 'Source interface address, may be numeric IP '
          'address or name of network device, ex: eth0.',
          default=None),
      Arg('interval_secs', int, 'The interval in seconds between two '
          'consecutive pings.',
          default=2),
      Arg('duration_secs', int, 'The duration of the ping test in seconds.',
          default=10),
      Arg('ping_success_percent', int, 'The percentage of successful pings '
          'to meet.  It will be checked at the end of the test.',
          default=70),
      Arg('moving_window_size', int, 'The size of the moving window in number '
          'of ping attempts.  If it is set, the percentage of successful '
          'pings will be checked within the moving window in addition to '
          'that at the end of the test.',
          default=None),
      Arg('verbose', bool, 'Dumps stdout of ping commands.',
          default=False),
      Arg('packet_size', int, 'Specifies the number of data bytes to be sent.',
          default=None),
  ]

  ui_class = test_ui.ScrollableLogUI

  def _CheckSuccessPercentage(self, success_count, total_count, title=''):
    """Checks the percentage of successful pings is within the range."""
    success_percentage = (success_count / total_count) * 100
    if success_percentage < self.args.ping_success_percent:
      self.FailTask(
          'Failed to meet ping success percentage: %.2f%% (expected: %d%%).' % (
              success_percentage, self.args.ping_success_percent))
    logging.info('%s%.2f%% packets received.', title, success_percentage)

  def runTest(self):
    """Tests the network connection by pinging a host for a period of time.

    Pings a host and counts the percentage of successful pings at the end of
    the test.  If moving_window_size is set, it will also check the successful
    percentage within the moving window during the ping tests.
    """
    window_size = self.args.moving_window_size
    moving_queue = []
    moving_success_count = 0
    total_success_count = 0
    total_count = 0

    ping_command = 'ping %s -c 1' % self.args.host
    if self.args.interface:
      ping_command += ' -I %s' % self.args.interface
    if self.args.packet_size:
      ping_command += ' -s %d' % self.args.packet_size

    end_time = time_utils.MonotonicTime() + self.args.duration_secs
    while time_utils.MonotonicTime() < end_time:
      if self.args.verbose:
        p = process_utils.Spawn(ping_command,
                                shell=True, log=True, read_stdout=True)
        logging.info(p.stdout_data)
        if total_count % 10 == 0:
          self.ui.ClearLog()
        self.ui.AppendLog(p.stdout_data + '\n')
      else:
        p = process_utils.Spawn(ping_command, shell=True, call=True,
                                ignore_stdout=True, ignore_stderr=True)
      result = int(p.returncode == 0)

      if window_size is not None:
        moving_success_count += result
        moving_queue.append(result)
        if len(moving_queue) > window_size:
          moving_success_count -= moving_queue.pop(0)
        if len(moving_queue) == window_size:
          self._CheckSuccessPercentage(
              moving_success_count, window_size, 'Moving average: ')

      total_success_count += result
      total_count += 1
      self.Sleep(self.args.interval_secs)

    self._CheckSuccessPercentage(total_success_count, total_count, 'Overall: ')
