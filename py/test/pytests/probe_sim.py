# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes SIM card information from 'modem status'.

The first usage of this test is to insert sim card, record ICCID (IMSI) value,
then remove sim card.
A 'modem reset' is needed after plugging SIM card.
It is not needed after removing SIM card.
The second usage of this test is to make sure that SIM card is not present.
A 'modem reset' is needed to avoid the case that SIM card is inserted without
a 'modem reset'.
Before running this test, modem carrier should be set to Generic UMTS.
"""

import logging
import re

from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

_SIM_PRESENT_RE = re.compile(r'IMSI: (\d{14,15})', re.IGNORECASE | re.MULTILINE)
_SIM_NOT_PRESENT_RE = re.compile(r'SIM: /$|No modems were found$',
                                 re.IGNORECASE | re.MULTILINE)

_INSERT_CHECK_PERIOD_SECS = 1
_INSERT_CHECK_MAX_WAIT = 60


class ProbeSIMCardTest(test_case.TestCase):
  ARGS = [
      Arg('only_check_simcard_not_present', bool,
          'Only checks sim card is not present', default=False),
      Arg('only_check_simcard_present', bool,
          'Only checks sim card is present', default=False),
      Arg('poll_modem_status', bool,
          'Polls modem status until the status is available', default=False),
      Arg('modem_reset_commands', list,
          'A list of commands to reset modem', default=[['modem', 'reset']]),
      Arg('enable_modem_reset', bool,
          'If true, reset modem before check status.', default=True)]

  def setUp(self):
    self.reset_commands = self.args.modem_reset_commands

  def runTest(self):
    if self.args.only_check_simcard_present:
      self.CheckSIMCardState(_SIM_PRESENT_RE,
                             'Fail to make sure sim card is present')
    elif self.args.only_check_simcard_not_present:
      self.CheckSIMCardState(_SIM_NOT_PRESENT_RE,
                             'Fail to make sure sim card is not present')
    else:
      self.ResetModem()
      self.ui.SetState(_('Please insert the SIM card'))
      match = self.WaitForSIMCard(_SIM_PRESENT_RE)
      iccid = match.group(1)
      logging.info('ICCID: %s', iccid)
      event_log.Log('SIM_CARD_DETECTION', ICCID=iccid)
      testlog.LogParam('ICCID', iccid)

      self.ui.SetState(_('Detected! Please remove the SIM card'))
      self.WaitForSIMCard(_SIM_NOT_PRESENT_RE)

  def ResetModem(self):
    """Resets modem."""
    if self.args.enable_modem_reset:
      for command in self.args.modem_reset_commands:
        process_utils.Spawn(command, call=True, log=True)
      self.Sleep(_INSERT_CHECK_PERIOD_SECS)

  def GetModemStatus(self):
    """Gets modem status."""
    status = process_utils.SpawnOutput(['modem', 'status'], log=True)
    if not status:
      status += process_utils.SpawnOutput(['mmcli', '-L'], log=True)
    return status

  def CheckSIMCardState(self, sim_re, fail_string):
    self.ui.SetState(_('Checking SIM card is present or not...'))

    self.ResetModem()

    output = self.GetModemStatus()
    if self.args.poll_modem_status:
      total_delay = 0
      while not output:
        self.Sleep(_INSERT_CHECK_PERIOD_SECS)
        total_delay += _INSERT_CHECK_PERIOD_SECS
        if total_delay >= _INSERT_CHECK_MAX_WAIT:
          self.FailTask(
              'Failed to detect sim in %d seconds' % _INSERT_CHECK_MAX_WAIT)
        output = self.GetModemStatus()

    logging.info(output)
    self.assertRegex(output, sim_re, fail_string)

  def WaitForSIMCard(self, sim_re):
    while True:
      output = self.GetModemStatus()
      logging.info(output)

      match = sim_re.search(output)
      if match:
        return match

      self.Sleep(_INSERT_CHECK_PERIOD_SECS)
