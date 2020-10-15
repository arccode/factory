# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This test cycles the battery.

It runs for a particular number of cycles or number of hours and records,
cycling the battery between a minimum charge (e.g., 5%) and a maximum
charge (e.g., 95%).  Cycle times are logged to event logs.
"""

import collections
import logging
import time

from cros.factory.device import device_utils
from cros.factory.test.event_log import Log
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import stress_manager
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


Mode = type_utils.Enum(['CHARGE', 'DISCHARGE', 'CUTOFF'])

History = collections.namedtuple('History', ['cycle', 'charge', 'discharge'])


class BatteryCycleTest(test_case.TestCase):
  ARGS = [
      Arg('num_cycles', int, 'Number of cycles to run', default=None),
      Arg('max_duration_hours', (int, float),
          'Maximum number of hours to run', default=None),
      Arg('cycle_timeout_secs', int,
          'Maximum time for one charge/discharge cycle', default=12 * 60 * 60),
      Arg('minimum_charge_pct', (int, float), 'Minimum charge, in percent',
          default=5),
      Arg('maximum_charge_pct', (int, float), 'Maximum charge, in percent',
          default=95),
      Arg('charge_threshold_secs', int,
          'Amount of time the charge must remain above or below the '
          'specified threshold to have considered to have finished '
          'part of a cycle.', default=30),
      Arg('idle_time_secs', int, 'Time to idle between battery checks.',
          default=1),
      Arg('log_interval_secs', int, 'Interval at which to log system status.',
          default=30),
      Arg('verify_cutoff', bool,
          'True to verify battery stops charging when ~100%',
          default=False),
      Arg('cutoff_charge_pct', (int, float),
          'Minimum charge level in percent allowed in cutoff state.',
          default=98),
      Arg('fast_discharge', bool,
          'Use stressapptest in discharge phase to discharge faster',
          default=True)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.status = self.dut.status.Snapshot()
    self.completed_cycles = 0
    self.mode = None
    self.start_time = time.time()
    self.cycle_start_time = None
    self.history = []  # Array of History objects
    self._UpdateHistory()

  def _Log(self, event, **kwargs):
    """Logs an event to the event log.

    The current mode, cycle, and system are also logged.

    Args:
      kwargs: Additional items to log.
    """
    log_args = dict(kwargs)
    log_args['mode'] = self.mode
    log_args['cycle'] = self.completed_cycles
    log_args['battery'] = self.dut.power.GetInfoDict()
    Log(event, **log_args)

  def _UpdateHistory(self):
    """Updates history in the UI."""
    history_lines = []
    for h in self.history[-5:]:
      line = ('%d: Charged in %s' % (h.cycle + 1,
                                     time_utils.FormatElapsedTime(h.charge)))
      if h.discharge:
        line += (
            ', discharged in %s' % time_utils.FormatElapsedTime(h.discharge))

      history_lines.append(test_ui.Escape(line))

    if not history_lines:
      history_lines.append('(none)')
    while len(history_lines) < 5:
      history_lines.append('')
    self.ui.SetHTML('\n'.join(history_lines), id='bc-history')

  def _RunPhase(self):
    """Runs the charge or discharge part of a cycle."""

    self._Log('phase_start')
    logging.info('Starting %s, cycle=%d', self.mode, self.completed_cycles)

    target_charge_map = {Mode.CHARGE: self.args.maximum_charge_pct,
                         Mode.DISCHARGE: self.args.minimum_charge_pct,
                         Mode.CUTOFF: 100}
    target_charge_pct = target_charge_map[self.mode]

    for elt_id, content in (
        ('bc-phase', 'Charging' if self.mode == Mode.CHARGE else 'Discharging'),
        ('bc-current-cycle', self.completed_cycles + 1),
        ('bc-cycles-remaining', (self.args.num_cycles - self.completed_cycles
                                 if self.args.num_cycles
                                 else u'\u221e')),
        ('bc-target-charge', '%.2f%%' % target_charge_pct)):
      self.ui.SetHTML(content, id=elt_id)

    first_done_time = [None]

    def IsDone():
      """Returns True if the cycle really is done.

      This is True if IsDoneNow() has been continuously true for
      charge_threshold_secs.
      """
      if is_done_now(self.dut.power.GetChargePct(True)):
        if not first_done_time[0]:
          logging.info('%s cycle appears to be done. '
                       'Will continue checking for %d seconds',
                       self.mode, self.args.charge_threshold_secs)
          first_done_time[0] = time.time()
        return (time.time() - first_done_time[0] >=
                self.args.charge_threshold_secs)

      if first_done_time[0]:
        logging.info('%s cycle now appears not to be done. '
                     'Resetting threshold.', self.mode)
        first_done_time[0] = None
      return False

    if self.mode in (Mode.CHARGE, Mode.CUTOFF):
      self.dut.power.SetChargeState(self.dut.power.ChargeState.CHARGE)
      stress_manager_instance = stress_manager.DummyStressManager(self.dut)
      if self.mode == Mode.CHARGE:
        is_done_now = lambda x: x > target_charge_pct
      else:
        is_done_now = lambda x: (self.dut.power.GetBatteryCurrent() == 0 and
                                 x > self.args.cutoff_charge_pct)
    else:
      self.dut.power.SetChargeState(self.dut.power.ChargeState.DISCHARGE)
      if self.args.fast_discharge:
        stress_manager_instance = stress_manager.StressManager(self.dut)
      else:
        stress_manager_instance = stress_manager.DummyStressManager(self.dut)
      is_done_now = lambda x: x < target_charge_pct

    phase_start_time = time.time()
    last_log_time = None
    with stress_manager_instance.Run():
      while True:
        self.status = self.dut.status.Snapshot()
        now = time.time()
        if (last_log_time is None or
            now - last_log_time >= self.args.log_interval_secs):
          last_log_time = now
          self._Log('status')

        if now > self.cycle_start_time + self.args.cycle_timeout_secs:
          self.fail('%s timed out' % self.mode)

        if IsDone():
          self._Log(
              'phase_end', duration_secs=(now - phase_start_time))
          logging.info('%s cycle completed in %d seconds',
                       self.mode, now - phase_start_time)

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
          self.ui.SetHTML(
              time_utils.FormatElapsedTime(elapsed_time)
              if elapsed_time else u'\u221e',
              id=elt_id)
        self.ui.SetHTML(
            '%.2f%%' % self.dut.power.GetChargePct(get_float=True),
            id='bc-charge')
        self.ui.SetHTML(
            '(complete in %s s)' % (self.args.charge_threshold_secs -
                                    int(round(now - first_done_time[0])))
            if first_done_time[0] else '',
            id='bc-phase-complete')

        self.Sleep(self.args.idle_time_secs)

  def runTest(self):
    try:
      self.start_time = time.time()
      while True:
        self.cycle_start_time = time.time()
        if (self.args.num_cycles and
            self.completed_cycles >= self.args.num_cycles):
          logging.info('Completed %s cycles (num_cycles).  Success.',
                       self.args.num_cycles)
          return

        duration_hours = (time.time() - self.start_time) / (60 * 60)
        if (self.args.max_duration_hours and
            duration_hours >= self.args.max_duration_hours):
          logging.info('Ran for %s hours.  Success.', duration_hours)
          return

        for mode in (Mode.CHARGE, Mode.DISCHARGE):
          self.mode = mode
          self._RunPhase()
        self.completed_cycles += 1

      if self.args.verify_cutoff:
        self.mode = Mode.CUTOFF
        self._RunPhase()

      self._Log('pass')
    except Exception:
      logging.exception('Test failed')
      error_msg = debug_utils.FormatExceptionOnly()
      self._Log('fail', error_msg=error_msg)
      self.FailTask(error_msg)
