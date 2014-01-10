# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a buzzer test."""

import random
import time
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.process_utils import Spawn

_MSG_BUZZER_INFO = test_ui.MakeLabel(
    'How many beeps do you hear? <br>'
    'Press space to start.',
    zh='你听到几声哔声？<br>'
    '压下空白键开始测试',
    css_class='buzzer-test-info')

_MSG_BUZZER_TEST = test_ui.MakeLabel(
    'How many beeps do you hear? <br>'
    'Press the number you hear to pass the test.<br>'
    'Press \'r\' to play again.',
    zh='你听到几声哔声？<br>'
    '请按下数字代表你听到几声哔声<br>'
    '按下 \'r\' 重播',
    css_class='buzzer-test-info')

_HTML_BUZZER = """
<table style="width: 70%%; margin: auto;">
  <tr>
    <td align="center"><div id="buzzer_title"></div></td>
  </tr>
</table>
"""

_CSS_BUZZER = """
  .buzzer-test-info { font-size: 2em; }
"""

_JS_BUZZER = """
window.onkeydown = function(event) {
  if (event.keyCode == 32 || event.keyCode == 82) { // space and 'R'
    test.sendTestEvent("StartTest", '');
  } else if (event.keyCode >= 48 && event.keyCode <= 57) { // 0 ~ 9
    test.sendTestEvent("CheckResult", event.keyCode - 48)
  }
}
"""

class BuzzerTest(unittest.TestCase):
  """Tests buzzer."""
  ARGS = [
    # Common arguments
    Arg('init_commands', list, 'Setup buzzer commands', optional=True),
    Arg('start_command', list, 'Start beep command', optional=True),
    Arg('stop_command', list, 'Stop beep command', optional=True),
    Arg('beep_duration_secs', float, 'How long for one beep', 0.3),
    Arg('mute_duration_secs', float, 'Mute duration between two beeps', 0.5),
  ]

  def setUp(self):
    self._pass_digit = random.randint(1, 5)
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_BUZZER)
    self.template.SetState(_HTML_BUZZER)
    self.ui.RunJS(_JS_BUZZER)
    self.ui.SetHTML(_MSG_BUZZER_INFO, id='buzzer_title')
    if self.args.init_commands:
      self.InitialBuzzer(self.args.init_commands)
    self.ui.AddEventHandler('StartTest', self.StartTest)
    self.ui.AddEventHandler('CheckResult', self.CheckResult)

  def InitialBuzzer(self, commands):
    for command in commands:
      Spawn(command, check_call=True)

  def BeepOne(self, start_cmd, stop_cmd):
    if start_cmd:
      Spawn(start_cmd, check_call=True)
    time.sleep(self.args.beep_duration_secs)
    if stop_cmd:
      Spawn(stop_cmd, check_call=True)

  def StartTest(self, event):  # pylint: disable=W0613
    self.ui.SetHTML(_MSG_BUZZER_TEST, id='buzzer_title')
    for i in xrange(self._pass_digit):  # pylint: disable=W0612
      self.BeepOne(self.args.start_command, self.args.stop_command)
      time.sleep(self.args.mute_duration_secs)

  def CheckResult(self, event):
    if event.data != self._pass_digit:
      self.ui.Fail('Wrong number to press.')
    else:
      self.ui.Pass()

  def runTest(self):
    self.ui.Run()
