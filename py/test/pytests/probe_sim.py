# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
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
import threading
import time
import unittest
import uuid

from cros.factory.event_log import Log
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.utils.process_utils import Spawn, SpawnOutput

_SIM_PRESENT_RE = r'IMSI: (\d{14,15})'
_SIM_NOT_PRESENT_RE = r'SIM: /$'

_TEST_TITLE = test_ui.MakeLabel('SIM Card Test', u'SIM卡测试')
_INSERT_SIM_INSTRUCTION = test_ui.MakeLabel(
    'Please insert the SIM card', u'請插入SIM卡')
_REMOVE_SIM_INSTRUCTION = test_ui.MakeLabel(
    'Detected! Please remove the SIM card', u'已經偵测SIM卡, 請移除SIM卡')
_CHECK_SIM_INSTRUCTION = test_ui.MakeLabel(
    'Checking SIM card is present or not...', u'检查SIM卡是否存在')

_INSERT_CHECK_PERIOD_SECS = 1
_INSERT_CHECK_MAX_WAIT = 60


class WaitSIMCardThread(threading.Thread):
  """The thread to wait for SIM card state.

  Args:
    simcard_event: ProbeSIMCardTask.INSERT_SIM_CARD or
        ProbeSIMCardTask.REMOVE_SIM_CARD
    on_success: The callback function to call upon success.
  """
  def __init__(self, simcard_event, on_success, force_stop):
    threading.Thread.__init__(self, name='WaitSIMCardThread')
    self._done = threading.Event()
    self._simcard_event = simcard_event
    self._on_success = on_success
    self._re_present = re.compile(_SIM_PRESENT_RE, re.MULTILINE | re.IGNORECASE)
    self._re_not_present = re.compile(_SIM_NOT_PRESENT_RE,
                                      re.MULTILINE | re.IGNORECASE)
    self._force_stop = force_stop
    self._force_stop.clear()

  def run(self):
    while not self._done.is_set() and not self._force_stop.is_set():
      # Only do modem reset when probing for insert event.
      # modem status will not show IMSI if sim card is removed even without
      # modem reset.
      if self._simcard_event == ProbeSIMCardTask.INSERT_SIM_CARD:
        Spawn(['modem', 'reset'], call=True, log=True)
      output = SpawnOutput(['modem', 'status'], log=True)
      logging.info(output)
      present = self._re_present.search(output)
      if present:
        logging.info('present')
      not_present = self._re_not_present.search(output)
      if not_present:
        logging.info('not present')

      if self._simcard_event == ProbeSIMCardTask.INSERT_SIM_CARD and present:
        logging.info('ICCID: %s', present.group(1))
        Log('SIM_CARD_DETECTION', ICCID=present.group(1))
        self.Detected()
      elif (self._simcard_event == ProbeSIMCardTask.REMOVE_SIM_CARD
            and not_present):
        self.Detected()
      else:
        self._done.wait(_INSERT_CHECK_PERIOD_SECS)

  def Detected(self):
    """Reports detected and stops the thread."""
    logging.info('%s detected', self._simcard_event)
    self._on_success()

    # This is needed to avoid race condition that _on_success
    # does not stop this thread before the next iteration.
    self.Stop()

  def Stop(self):
    """Stops the thread."""
    self._done.set()


class ProbeSIMCardTask(FactoryTask):
  """Probe SIM card task."""
  INSERT_SIM_CARD = 'Insertion'
  REMOVE_SIM_CARD = 'Removal'

  def __init__(self, test, instruction, simcard_event):
    super(ProbeSIMCardTask, self).__init__()
    self._ui = test.ui
    self._template = test.template
    self._force_stop = test.force_stop
    self._instruction = instruction
    self._wait_sim = WaitSIMCardThread(simcard_event,
        self.PostSuccessEvent, self._force_stop)
    self._pass_event = str(uuid.uuid4())

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass()"""
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT,
                             subtype=self._pass_event))

  def Run(self):
    self._template.SetState(self._instruction)
    self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
    self._wait_sim.start()

  def Cleanup(self):
    self._wait_sim.Stop()


class InsertSIMTask(ProbeSIMCardTask):
  """Task to wait for SIM card insertion"""
  def __init__(self, test):
    super(InsertSIMTask, self).__init__(test, _INSERT_SIM_INSTRUCTION,
          ProbeSIMCardTask.INSERT_SIM_CARD)


class RemoveSIMTask(ProbeSIMCardTask):
  """Task to wait for SIM card removal"""
  def __init__(self, test):
    super(RemoveSIMTask, self).__init__(test, _REMOVE_SIM_INSTRUCTION,
          ProbeSIMCardTask.REMOVE_SIM_CARD)


class CheckSIMTask(FactoryTask):
  """Task to check SIM card state"""
  def __init__(self, test):
    super(CheckSIMTask, self).__init__()
    self._template = test.template
    self._args = test.args

  def CheckSIMCardState(self, sim_re, fail_string):
    self._template.SetState(_CHECK_SIM_INSTRUCTION)
    Spawn(['modem', 'reset'], call=True, log=True)
    output = SpawnOutput(['modem', 'status'], log=True)
    if self._args.poll_modem_status:
      total_delay = 0
      while not output:
        time.sleep(_INSERT_CHECK_PERIOD_SECS)
        output = SpawnOutput(['modem', 'status'], log=True)
        total_delay += _INSERT_CHECK_PERIOD_SECS
        if total_delay >= _INSERT_CHECK_MAX_WAIT:
          self.Fail('Failed to detect sim in ' +
                    str(_INSERT_CHECK_MAX_WAIT) + ' seconds')
          return
    logging.info(output)
    if not re.compile(sim_re, re.MULTILINE | re.IGNORECASE).search(output):
      self.Fail(fail_string)
    else:
      self.Pass()

  def Run(self):
    if self._args.only_check_simcard_present:
      self.CheckSIMCardState(_SIM_PRESENT_RE,
                             'Fail to make sure sim card is present')
    elif self._args.only_check_simcard_not_present:
      self.CheckSIMCardState(_SIM_NOT_PRESENT_RE,
                             'Fail to make sure sim card is not present')


class ProbeSIMCardTest(unittest.TestCase):
  ARGS = [
      Arg('only_check_simcard_not_present', bool,
          'Only checks sim card is not present', default=False),
      Arg('only_check_simcard_present', bool,
          'Only checks sim card is present', default=False),
      Arg('poll_modem_status', bool,
          'Polls modem status until the status is available', default=False)]

  def setUp(self):
    self.force_stop = threading.Event()

    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self._task_manager = None

  def runTest(self):
    self.template.SetTitle(_TEST_TITLE)

    def Done():
      self.force_stop.set()

    if (self.args.only_check_simcard_not_present or
        self.args.only_check_simcard_present):
      task_list = [CheckSIMTask(self)]
    else:
      task_list = [InsertSIMTask(self), RemoveSIMTask(self)]

    self._task_manager = FactoryTaskManager(
        self.ui, task_list, on_finish=Done)

    self._task_manager.Run()
