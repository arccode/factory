# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Displays a message.

The operator can press the space or enter key to proceed.
It can also be automatically proceed if we specify argument 'seconds'.
"""


from __future__ import print_function
import time
import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneSection


CSS_TEMPLATE = """
.message { font-size: %(text_size)s%%; color: %(text_color)s; }
.state { background-color: %(background_color)s; }
"""
_HTML_REMAIN = '<br><div id="remain"></div>'


class ShowingTask(FactoryTask):
  """The task to show message for seconds """
  def __init__(self, ui, seconds):  # pylint: disable=W0231
    self._ui = ui
    self._seconds = seconds
    self._done = False

    self._ui.BindKey(test_ui.SPACE_KEY, lambda _: self.Done())
    self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self.Done())

  def Done(self):
    self._done = True

  def Run(self):
    seconds = self._seconds
    while seconds != 0 and not self._done:
      self._ui.SetHTML(str(seconds), id='remain')
      time.sleep(1)
      seconds = seconds - 1
    self.Pass()


class MessageTest(unittest.TestCase):
  """A factory test to display a message."""
  ARGS = [
      Arg('html_en', str, 'Message (HTML in English).'),
      Arg('html_zh', (str, unicode), ' Message (HTML, in Chinese).',
          optional=True),
      Arg('text_size', str, 'size of message in percentage', default='200'),
      Arg('text_color', str, 'color of message (in CSS)', default='black'),
      Arg('background_color', str, 'background color (in CSS)',
          default='white'),
      Arg('seconds', int, 'duration to display message.'
          'Specify None to show until key press.',
          default=None, optional=True)
  ]

  def runTest(self):
    css = (CSS_TEMPLATE %
           dict(text_size=self.args.text_size,
                text_color=self.args.text_color,
                background_color=self.args.background_color))
    ui = UI(css=css)
    template = OneSection(ui)
    template.SetTitle(MakeLabel('Message', '讯息'))
    template.SetState(
        '<div class="state">' +
        MakeLabel(self.args.html_en, self.args.html_zh, 'message') +
        _HTML_REMAIN +
        '</div>')
    if self.args.seconds:
      task = ShowingTask(ui, self.args.seconds)
      FactoryTaskManager(ui, [task]).Run()
    else:
      ui.BindStandardKeys(bind_fail_keys=False)
      ui.Run()
