# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Ping connection test.

Tests network connection by pinging a host for a period of time.  Then
checks the percentage of successful pings is above some threshold or not.
If moving_window_size is set, it will check the percentage within the
moving window during the test.  It always checks the percentage of
successful pings for the whole duration at the end of the test.

Usage examples::

    # Pings 192.168.0.1 every 10 seconds for 120 seconds.
    # Checks the successful pings are >= 60% at the end of the test.
    OperatorTest(
        id='ping_test',
        pytest_name='ping_test',
        dargs={'host': '192.168.0.1',
               'interval_secs': 10,
               'duration_secs': 120,
               'ping_success_percent': 60})

    # Pings 192.168.0.1 every 10 seconds for 120 seconds.
    # Checks the successful pings are >= 60% within the moving
    # window of 5 pings.  It also checks the successful pings
    # are >= 60% overall.
    OperatorTest(
        id='ping_test',
        pytest_name='ping_test',
        dargs={'host': '192.168.0.1',
               'interval_secs': 10,
               'duration_secs': 120,
               'ping_success_percent': 60,
               'moving_window_size': 5})
"""

from __future__ import print_function

import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import time_utils

_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Ping test')
_CSS = '#state {text-align:left;}'


class PingTest(unittest.TestCase):
  ARGS = [
      Arg('host', str, 'The IP address or hostname to ping.',
          optional=False),
      Arg('interface', str, 'Source interface address, may be numeric IP '
          'address or name of network device, ex: eth0.',
          default=None, optional=True),
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
          default=None, optional=True),
      Arg('verbose', bool, 'Dumps stdout of ping commands.',
          default=False),
      Arg('packet_size', int, 'Specifies the number of data bytes to be sent.',
          default=None, optional=True),
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def _CheckSuccessPercentage(self, success_count, total_count, title=''):
    """Checks the percentage of successful pings is within the range."""
    success_percentage = (float(success_count) / total_count) * 100
    if success_percentage < self.args.ping_success_percent:
      self._ui.Fail(
          'Failed to meet ping success percentage: %.2f%% (expected: %d%%).' % (
              success_percentage, self.args.ping_success_percent))
    logging.info(title + '%.2f%% packets received.', success_percentage)

  def _PingTest(self):
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
        self._template.SetState(
            test_ui.Escape(p.stdout_data),
            append=(True if total_count % 10 else False))
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
      time.sleep(self.args.interval_secs)

    self._CheckSuccessPercentage(total_success_count, total_count, 'Overall: ')
    # Passes the test if all checks above are good.
    self._ui.Pass()

  def runTest(self):
    self._ui.Run(blocking=False)
    self._PingTest()
