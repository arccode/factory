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
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.arg_utils import Arg


CSS_TEMPLATE = """
.message { font-size: %(text_size)s%%; color: %(text_color)s; }
.state { background-color: %(background_color)s; }
"""
_HTML_REMAIN = '<br><div id="remain"></div>'


class ShowingTask(FactoryTask):
  """The task to show message for seconds """
  def __init__(self, ui, seconds, manual_check):  # pylint: disable=W0231
    self._ui = ui
    self._seconds = seconds
    self._done = False

    self._ui.BindKey(test_ui.SPACE_KEY, lambda _: self.Done())
    self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self.Done())
    if manual_check:
      self._ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.Fail(None))

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
          default=None, optional=True),
      Arg('manual_check', bool, 'If set to true, operator can press ESC to '
          'fail the test case.', default=False, optional=True),
      Arg('show_press_button_hint', bool, 'If set to true, will show addition '
          'message to ask operators to press the button.', default=False,
          optional=True),
  ]

  def runTest(self):
    css = (CSS_TEMPLATE %
           dict(text_size=self.args.text_size,
                text_color=self.args.text_color,
                background_color=self.args.background_color))
    ui = UI(css=css)
    template = OneSection(ui)

    press_button_hint = ''
    if self.args.show_press_button_hint:
      if self.args.manual_check:
        press_button_hint = MakeLabel(
            ('<div>Press <strong>Enter</strong> to continue, '
             'or <strong>ESC</strong> if things are not going right.</div>'),
            (u'<div>按<strong>Enter</strong>继续，'
             u'不正确请按<strong>ESC</strong></div>'), None)
      else:
        press_button_hint = MakeLabel(
            '<div>Press <strong>Enter</strong> to continue.</div>',
            u'<div>按<strong>Enter</strong>继续</div>', None)

    template.SetTitle(MakeLabel('Message', u'讯息'))
    template.SetState(
        '<div class="state">' +
        MakeLabel(self.args.html_en, self.args.html_zh, 'message') +
        press_button_hint +
        _HTML_REMAIN +
        '</div>')
    if self.args.seconds:
      task = ShowingTask(ui, self.args.seconds, self.args.manual_check)
      FactoryTaskManager(ui, [task]).Run()
    else:
      ui.BindStandardKeys(bind_fail_keys=self.args.manual_check)
      ui.Run()
