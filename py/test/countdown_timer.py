# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time

from cros.factory.test.test_ui import MakeLabel
from cros.factory.test.utils import StartDaemonThread

_MSG_TIME_REMAINING = lambda t: MakeLabel('Time remaining: %d' % t,
                                          u'剩余时间：%d' % t)


def StartCountdownTimer(timeout_secs, timeout_handler, ui, element_id):
  """Starts a daemon thread for CountdownTimer and updates factory UI.

  It updates UI for time remaining and calls timeout_handler when timeout.

  Usage:
    Inside a factory test's setUp method:
      StartCountdownTimer(self.args.timeout_secs,
                          self.TimeoutHandler,
                          self.ui,
                          _ID_COUNTDOWN_TIMER)

  Args:
    timeout_secs: (int) #seconds to timeout.
    timeout_handler: (callback) called when timeout reaches.
    ui: a test_ui.UI instance.
    element_id: The HTML element to place time remaining info.
  """
  tick = lambda t: ui.SetHTML(_MSG_TIME_REMAINING(t), id=element_id)
  StartDaemonThread(target=CountdownTimer,
                    args=(timeout_secs, timeout_handler, tick))


def CountdownTimer(timeout_secs, timeout_handler, tick=None):
  """A countdown timer.

  It calls timeout_handler when the countdown is over. During the countdown,
  it calls tick every second if provided.

  Args:
    timeout_secs: (int) #seconds to timeout.
    timeout_handler: (callback) called when timeout reaches.
    tick: (optional callback) called with a remaining seconds every seconds.
  """
  time_remaining = timeout_secs
  while time_remaining > 0:
    if tick:
      tick(time_remaining)
    time.sleep(1)
    time_remaining -= 1
  timeout_handler()
