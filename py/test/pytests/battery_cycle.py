#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This test cycles the battery.

It runs for a particular number of cycles or number of hours and records,
cycling the battery between a minimum charge (e.g., 5%) and a maximum
charge (e.g., 95%).  Cycle times are logged to event logs.
"""


import collections
import logging
import multiprocessing
import operator
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.event_log import Log
from cros.factory.system import Board, SystemStatus
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.utils import Enum
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess
from cros.factory.utils.time_utils import FormatElapsedTime


Mode = Enum(['CHARGE', 'DISCHARGE'])

History = collections.namedtuple('History', ['cycle', 'charge', 'discharge'])

CSS = """
table {
  margin: auto;
}
th {
  padding-left: 5em;
}
td {
  padding: 1px 8px;
  min-width: 15em;
}
"""

HTML = """
<table>
  <tr><th>Current cycle count:</th><td id="bc-current-cycle"></td></tr>
  <tr><th>Cycles remaining:</th><td id="bc-cycles-remaining"></td></tr>
  <tr>
    <th>Phase:</th>
    <td><span id="bc-phase"></span> <span id="bc-phase-complete"></span></td>
  </tr>
  <tr>
    <th>Elapsed time in this phase:</th>
    <td id="bc-phase-elapsed-time"></td>
  </tr>
  <tr>
    <th>Elapsed time in this cycle:</th>
    <td id="bc-cycle-elapsed-time"></td>
  </tr>
  <tr><th>Total elapsed time:</th><td id="bc-elapsed-time"></td></tr>
  <tr><th>Total time remaining:</th><td id="bc-time-remaining"></td></tr>
  <tr><th>Current charge:</th><td id="bc-charge"></td></tr>
  <tr><th>Target charge:</th><td id="bc-target-charge"></td></tr>
  <tr><th>Previous cycle times:</th><td id="bc-history"></td></tr>
</table>
"""


class BatteryCycleTest(unittest.TestCase):
  ARGS = [
      Arg('num_cycles', int, 'Number of cycles to run', optional=True),
      Arg('max_duration_hours', (int, float),
          'Maximum number of hours to run', optional=True),
      Arg('cycle_timeout_secs', int,
          'Maximum time for one charge/discharge cycle', 12*60*60),
      Arg('minimum_charge_pct', (int, float), 'Minimum charge, in percent', 5),
      Arg('maximum_charge_pct', (int, float), 'Maximum charge, in percent', 95),
      Arg('charge_threshold_secs', int,
          'Amount of time the charge must remain above or below the '
          'specified threshold to have considered to have finished '
          'part of a cycle', 30),
      Arg('idle_time_secs', int, 'Time to idle between battery checks.', 1),
      Arg('log_interval_secs', int, 'Interval at which to log system status',
          30),
      ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.status = SystemStatus()
    self.template = ui_templates.OneSection(self.ui)
    self.template.SetState(HTML)
    self.ui.AppendCSS(CSS)
    self.board = system.GetBoard()
    self.completed_cycles = 0
    self.mode = None
    self.start_time = time.time()
    self.cycle_start_time = None
    self.history = []  # Arry of History objects
    self._UpdateHistory()

  def runTest(self):
    utils.StartDaemonThread(target=self._Run)
    self.ui.Run()

  def _GetChargePct(self):
    """Returns the current charge as a percentage."""
    return (self.status.battery['charge_now'] * 100.0 /
            self.status.battery['charge_full'])

  def _Log(self, event, **kwargs):
    """Logs an event to the event log.

    The current mode, cycle, and system are also logged.

    Args:
      kwargs: Additional items to log.
    """
    log_args = dict(kwargs)
    log_args['mode'] = self.mode
    log_args['cycle'] = self.completed_cycles
    log_args['status'] = self.status.__dict__
    Log(event, **log_args)

  def _UpdateHistory(self):
    """Updates history in the UI."""
    history_lines = []
    for h in self.history[-5:]:
      history_lines.append('%d: Charged in %s' %
                           (h.cycle + 1,
                            FormatElapsedTime(h.charge)))
      if h.discharge:
        history_lines[-1] += (', discharged in %s' %
                              FormatElapsedTime(h.discharge))

    if not history_lines:
      history_lines.append('(none)')
    while len(history_lines) < 5:
      history_lines.append('&nbsp')
    self.ui.SetHTML('<br>'.join(history_lines), id='bc-history')

  def _RunPhase(self):
    """Runs the charge or discharge part of a cycle."""
    self._Log('phase_start')
    logging.info('Starting %s, cycle=%d', self.mode, self.completed_cycles)
    target_charge_pct = (self.args.maximum_charge_pct
                         if self.mode == Mode.CHARGE
                         else self.args.minimum_charge_pct)
    comparator = operator.ge if self.mode == Mode.CHARGE else operator.le

    for elt_id, content in (
        ('bc-phase', 'Charging' if self.mode == Mode.CHARGE else 'Discharging'),
        ('bc-current-cycle', self.completed_cycles + 1),
        ('bc-cycles-remaining', (self.args.num_cycles - self.completed_cycles
                              if self.args.num_cycles
                              else u'∞')),
        ('bc-target-charge', '%.2f%%' % target_charge_pct)):
      self.ui.SetHTML(content, id=elt_id)

    def IsDoneNow():
      """Returns True if the cycle looks at this instant to be complete."""
      return comparator(self._GetChargePct(), target_charge_pct)

    first_done_time = [None]
    def IsDone():
      """Returns True if the cycle really is done.

      This is True if IsDoneNow() has been continuously true for
      charge_threshold_secs.
      """
      if IsDoneNow():
        if not first_done_time[0]:
          logging.info('%s cycle appears to be done. '
                       'Will continue checking for %d seconds',
                       self.mode, self.args.charge_threshold_secs)
          first_done_time[0] = time.time()
        return (time.time() - first_done_time[0] >=
                self.args.charge_threshold_secs)
      else:
        if first_done_time[0]:
          logging.info('%s cycle now appears not to be done. '
                       'Resetting threshold.', self.mode)
          first_done_time[0] = None
        return False

    processes = []

    try:
      if self.mode == Mode.CHARGE:
        self.board.SetChargeState(Board.ChargeState.CHARGE)
      else:
        self.board.SetChargeState(Board.ChargeState.DISCHARGE)
        # Start one process per core to spin the CPU to heat things up a
        # bit.
        for _ in xrange(multiprocessing.cpu_count()):
          processes.append(
              Spawn(['nice', 'python', '-c',
                     'import random\n'
                     'while True:\n'
                     '  x = random.random()']))

      phase_start_time = time.time()
      last_log_time = None
      while True:
        self.status = SystemStatus()
        now = time.time()
        if (last_log_time is None) or (
            now - last_log_time >= self.args.log_interval_secs):
          last_log_time = now
          self._Log('status')

        if now > self.cycle_start_time + self.args.cycle_timeout_secs:
          self.fail('%s timed out' % self.mode)
          return
        if IsDone():
          self._Log(
              'phase_end', duration_secs=(now - phase_start_time))
          logging.info('%s cycle completed in %d seconds',
                       self.mode, now - phase_start_time)

          # pylint: disable=W0212
          if self.history and self.history[-1].discharge is None:
            self.history[-1] = self.history[-1]._replace(
                discharge=(now - phase_start_time))
          else:
            self.history.append(History(self.completed_cycles,
                                        now - phase_start_time,
                                        None))
          self._UpdateHistory()
          return

        for elt_id, elapsed_time in (
            ('bc-elapsed-time', now - self.start_time),
            ('bc-cycle-elapsed-time', now - self.cycle_start_time),
            ('bc-phase-elapsed-time', now - phase_start_time),
            ('bc-time-remaining', (
                self.args.max_duration_hours * 60 * 60 -
                (now - phase_start_time)
                if self.args.max_duration_hours else None))):
          self.ui.SetHTML(FormatElapsedTime(elapsed_time)
                          if elapsed_time else '∞',
                          id=elt_id)
        self.ui.SetHTML('%.2f%%' % self._GetChargePct(), id='bc-charge')
        self.ui.SetHTML(
            '(complete in %s s)' % (self.args.charge_threshold_secs -
                                    int(round(now - first_done_time[0])))
            if first_done_time[0]
            else '',
            id='bc-phase-complete')

        time.sleep(self.args.idle_time_secs)
    finally:
      # Terminate any processes we created (to help discharge along).
      errors = []
      for p in processes:
        if p.poll() is None:
          TerminateOrKillProcess(p)
        else:
          # It shouldn't have died yet!
          errors.append('Process %d terminated with return code %d' %
                        p.pid, p.returncode)
      if errors:
        self.fail('; '.join(errors))

  def _Run(self):
    try:
      self.start_time = time.time()
      while True:
        self.cycle_start_time = time.time()
        if (self.args.num_cycles and
            self.completed_cycles >= self.args.num_cycles):
          logging.info('Completed %s cycles (num_cycles).  Success.',
                       self.args.num_cycles)
          self.ui.Pass()
          break

        duration_hours = (time.time() - self.start_time) / (60. * 60.)
        if (self.args.max_duration_hours and
            duration_hours >= self.args.max_duration_hours):
          logging.info('Ran for %s hours.  Success.', duration_hours)
          self.ui.Pass()
          break

        for mode in (Mode.CHARGE, Mode.DISCHARGE):
          self.mode = mode
          self._RunPhase()
        self.completed_cycles += 1

      self._Log('pass')
      self.ui.Pass()
    except:  # pylint: disable=W0702
      logging.exception('Test failed')
      error_msg = utils.FormatExceptionOnly()
      self._Log('fail', error_msg=error_msg)
      self.ui.Fail(error_msg)
