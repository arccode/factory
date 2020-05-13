# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a buzzer test."""

import random
import time

from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


_MAX_BEEP_TIMES = 5


class BuzzerTest(test_case.TestCase):
  """Tests buzzer."""
  ARGS = [
      # Common arguments
      Arg('init_commands', list, 'Setup buzzer commands', None),
      Arg('start_command', list, 'Start beep command', None),
      Arg('stop_command', list, 'Stop beep command', None),
      Arg('beep_duration_secs', float, 'How long for one beep', 0.3),
      Arg('mute_duration_secs', float, 'Mute duration between two beeps', 0.5),
  ]

  def setUp(self):
    self._pass_digit = random.randint(1, _MAX_BEEP_TIMES)
    self.ui.ToggleTemplateClass('font-large', True)
    if self.args.init_commands:
      self.InitialBuzzer(self.args.init_commands)

  def InitialBuzzer(self, commands):
    for command in commands:
      process_utils.Spawn(command, check_call=True)

  def BeepOne(self, start_cmd, stop_cmd):
    if start_cmd:
      process_utils.Spawn(start_cmd, check_call=True)
    self.Sleep(self.args.beep_duration_secs)
    if stop_cmd:
      process_utils.Spawn(stop_cmd, check_call=True)

  def runTest(self):
    max_total_duration = _MAX_BEEP_TIMES * (
        self.args.beep_duration_secs + self.args.mute_duration_secs)

    self.ui.SetState(_('How many beeps do you hear? <br>Press space to start.'))
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self.ui.SetState(
        _('How many beeps do you hear? <br>'
          'Press the number you hear to pass the test.<br>'
          "Press 'r' to play again."))

    while True:
      start_time = time.time()
      for unused_i in range(self._pass_digit):
        self.BeepOne(self.args.start_command, self.args.stop_command)
        self.Sleep(self.args.mute_duration_secs)
      # Try to make the test always run for about same duration, to avoid
      # cheating by looking at when the buttons appear.
      self.Sleep(max_total_duration - (time.time() - start_time))

      all_keys = [str(num + 1) for num in range(_MAX_BEEP_TIMES)] + ['R']
      key = self.ui.WaitKeysOnce(all_keys)
      if key != 'R':
        self.assertEqual(self._pass_digit, int(key), 'Wrong number to press.')
        return
