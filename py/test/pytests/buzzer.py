# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a buzzer test."""

import random
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

_MSG_BUZZER_INFO = i18n_test_ui.MakeI18nLabel(
    'How many beeps do you hear? <br>'
    'Press space to start.')

_MSG_BUZZER_TEST = i18n_test_ui.MakeI18nLabel(
    'How many beeps do you hear? <br>'
    'Press the number you hear to pass the test.<br>'
    "Press 'r' to play again.")

_HTML_BUZZER = '<div id="buzzer-title"></div>'

_CSS_BUZZER = """
  #buzzer-title {
    font-size: 2em;
    width: 70%;
  }
"""

_MAX_BEEP_TIMES = 5


class BuzzerTest(test_ui.TestCaseWithUI):
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
    self._pass_digit = random.randint(1, _MAX_BEEP_TIMES)
    self.ui.AppendCSS(_CSS_BUZZER)
    self.template.SetState(_HTML_BUZZER)
    if self.args.init_commands:
      self.InitialBuzzer(self.args.init_commands)

  def InitialBuzzer(self, commands):
    for command in commands:
      process_utils.Spawn(command, check_call=True)

  def BeepOne(self, start_cmd, stop_cmd):
    if start_cmd:
      process_utils.Spawn(start_cmd, check_call=True)
    time.sleep(self.args.beep_duration_secs)
    if stop_cmd:
      process_utils.Spawn(stop_cmd, check_call=True)

  def runTest(self):
    max_total_duration = _MAX_BEEP_TIMES * (
        self.args.beep_duration_secs + self.args.mute_duration_secs)

    self.ui.SetHTML(_MSG_BUZZER_INFO, id='buzzer-title')
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self.ui.SetHTML(_MSG_BUZZER_TEST, id='buzzer-title')

    while True:
      start_time = time.time()
      for unused_i in xrange(self._pass_digit):
        self.BeepOne(self.args.start_command, self.args.stop_command)
        time.sleep(self.args.mute_duration_secs)
      # Try to make the test always run for about same duration, to avoid
      # cheating by looking at when the buttons appear.
      time.sleep(max(0, max_total_duration - (time.time() - start_time)))

      all_keys = [str(num + 1) for num in range(_MAX_BEEP_TIMES)] + ['R']
      key = self.ui.WaitKeysOnce(all_keys)
      if key != 'R':
        self.assertEqual(self._pass_digit, int(key), 'Wrong number to press.')
        return
