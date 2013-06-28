# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes SIM card tray

Detects SIM card tray by GPIO.

Args:
  tray_already_present:SIM card tray is in machine before test starts.
  tray_detection_gpio: SIM card tray detection gpio number.
"""

import logging
import os
import threading
import time
import unittest
import uuid

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.utils.file_utils import WriteFile, ReadLines


_TEST_TITLE = test_ui.MakeLabel('SIM Card Tray Test', u'SIM卡卡盘测试')
_INSERT_TRAY_INSTRUCTION = test_ui.MakeLabel(
    'Please insert the SIM card tray', u'請插入SIM卡卡盘',
    'instruction-font-size')
_REMOVE_TRAY_INSTRUCTION = test_ui.MakeLabel(
    'Detected! Please remove the SIM card tray', u'已經偵测SIM卡卡盘, 請移除SIM卡卡盘',
    'instruction-font-size')

_CSS = """
.instruction-font-size {
  font-size: 2em;
}
"""


_INSERT_CHECK_PERIOD_SECS = 1
_GPIO_PATH = os.path.join('/sys', 'class', 'gpio')


class WaitTrayThread(threading.Thread):
  """The thread to wait for SIM card tray state.

  Args:
    get_detect: function to probe sim card tray. Returns ProbeTrayTask.INSERT
      or ProbeTrayTask.REMOVE.
    tray_event: The target tray event. ProbeTrayTask.INSERT or
      ProbeTrayTask.REMOVE.
    on_success: The callback function when tray_event is detected.
    force_stop: A threading.Event for user to stop the thread.
  """
  def __init__(self, get_detect, tray_event, on_success, force_stop):
    threading.Thread.__init__(self, name='WaitTrayThread')
    self._get_detect = get_detect
    self._tray_event = tray_event
    self._on_success = on_success
    self._force_stop = force_stop
    self._force_stop.clear()

  def run(self):
    while not self._force_stop.is_set():
      ret = self._get_detect()
      if self._tray_event == ret:
        self.Detected()
        return
      time.sleep(_INSERT_CHECK_PERIOD_SECS)

  def Detected(self):
    """Reports detected and stops the thread."""
    logging.info('%s detected', self._tray_event)
    factory.console.info('%s detected', self._tray_event)
    self._on_success()


class ProbeTrayTask(FactoryTask):
  """Probe SIM card tray task."""
  INSERT = 'Insert'
  REMOVE = 'Remove'

  def __init__(self, test, instruction, tray_event):
    super(ProbeTrayTask, self).__init__()
    self._ui = test.ui
    self._template = test.template
    self._instruction = instruction
    self._tray_event = tray_event
    self._wait_tray = WaitTrayThread(test.GetDetection,
        self._tray_event, self.PostSuccessEvent, test.force_stop)
    self._pass_event = str(uuid.uuid4())

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass()

    It is called by another thread. It ensures that self.Pass() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT,
                             subtype=self._pass_event))

  def Run(self):
    self._template.SetState(self._instruction)
    self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
    self._wait_tray.start()


class InsertTrayTask(ProbeTrayTask):
  """Task to wait for SIM card tray insertion"""
  def __init__(self, test):
    super(InsertTrayTask, self).__init__(test, _INSERT_TRAY_INSTRUCTION,
          ProbeTrayTask.INSERT)


class RemoveTrayTask(ProbeTrayTask):
  """Task to wait for SIM card tray removal"""
  def __init__(self, test):
    super(RemoveTrayTask, self).__init__(test, _REMOVE_TRAY_INSTRUCTION,
          ProbeTrayTask.REMOVE)


class ProbeTrayException(Exception):
  pass


class ProbeSimCardTrayTest(unittest.TestCase):
  ARGS = [
      Arg('tray_already_present', bool,
          'SIM card tray is in machine before test starts', default=False),
      Arg('tray_detection_gpio', int,
          'SIM card tray detection gpio number', default=159),
      Arg('only_check_presence', bool,
          'Only checks sim card tray presence matches tray_already_present. '
          'No user interaction required', default=True)]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self._task_manager = None
    self._detection_gpio_path = os.path.join(_GPIO_PATH,
        'gpio%d' % self.args.tray_detection_gpio)
    self.force_stop = threading.Event()

  def ExportGPIO(self):
    """Exports GPIO of tray detection pin.

    Raises:
      ProbeTrayException if gpio can not be exported.
    """
    if os.path.exists(self._detection_gpio_path):
      logging.info('gpio %s was exported before', self._detection_gpio_path)
      return
    export_path = os.path.join(_GPIO_PATH, 'export')
    try:
      WriteFile(export_path, str(self.args.tray_detection_gpio), True)
    except IOError:
      logging.exception('Can not write %s into %s',
                        str(self.args.tray_detection_gpio), export_path)
      raise ProbeTrayException('Can not export detection gpio %s' %
                               self.args.tray_detection_gpio)

  def GetDetection(self):
    """Returns tray status ProbeTrayTask.INSERT or ProbeTrayTask.REMOVE."""
    value_path = os.path.join(self._detection_gpio_path, 'value')
    lines = ReadLines(value_path)
    if not lines:
      raise ProbeTrayException('Can not get detection result from %s' %
                               value_path)
    ret = lines[0].strip()
    if ret not in ['0', '1']:
      raise ProbeTrayException('Get invalid detection %s from %s',
                               ret, value_path)
    return ProbeTrayTask.INSERT if ret == '1' else ProbeTrayTask.REMOVE

  def CheckPresence(self):
    self.assertEquals(
        self.args.tray_already_present,
        self.GetDetection() == ProbeTrayTask.INSERT,
        ('Unexpected tray %s' % (
             'absence. ' if self.args.tray_already_present else 'presence. ') +
         'Please %s SIM card tray and retest.' % (
             'insert' if self.args.tray_already_present else 'remove')))

  def runTest(self):
    self.template.SetTitle(_TEST_TITLE)
    self._detection_gpio_path = os.path.join(_GPIO_PATH,
        'gpio%d' % self.args.tray_detection_gpio)
    self.ExportGPIO()
    self.CheckPresence()

    if self.args.only_check_presence:
      factory.console.info('Passes the test that only checks presence is %s.' %
          self.args.tray_already_present)
      return

    if self.args.tray_already_present:
      task_list = [RemoveTrayTask(self),
                   InsertTrayTask(self)]
    else:
      task_list = [InsertTrayTask(self),
                   RemoveTrayTask(self)]

    def Done():
      self.force_stop.set()

    self._task_manager = FactoryTaskManager(self.ui, task_list, on_finish=Done)
    self._task_manager.Run()
