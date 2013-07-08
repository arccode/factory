# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import threading
import time

from cros.factory.test.test_ui import MakeLabel
from cros.factory.test.utils import StartDaemonThread

_MSG_TIME_REMAINING = lambda t: MakeLabel('Time remaining: %d' % t,
                                          u'剩余时间：%d' % t)


def StartCountdownTimer(timeout_secs, timeout_handler, ui, element_id,
                        disable_event=None):
  """Starts a thread for CountdownTimer and updates factory UI.

  It updates UI for time remaining and calls timeout_handler when timeout.
  The thread is a daemon thread if disable_event is None.

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
    disable_event: a threading.Event object to stop timer.
  """
  tick = lambda t: ui.SetHTML(_MSG_TIME_REMAINING(t), id=element_id)
  if disable_event:
    thread = threading.Thread(target=CountdownTimer,
        args=(timeout_secs, timeout_handler, tick, disable_event))
    thread.start()
  else:
    StartDaemonThread(target=CountdownTimer,
                      args=(timeout_secs, timeout_handler, tick))


def CountdownTimer(timeout_secs, timeout_handler, tick=None,
                   disable_event=None):
  """A countdown timer.

  It calls timeout_handler when the countdown is over. During the countdown,
  it calls tick every second if provided.
  It stops when disable_event is set if it is provided.

  Args:
    timeout_secs: (int) #seconds to timeout.
    timeout_handler: (callback) called when timeout reaches.
    tick: (optional callback) called with a remaining seconds every seconds.
    disable_event: a threading.Event object to stop timer.
  """
  logging.info('Timer is up with timeout_secs: %d', timeout_secs)
  end_time = time.time() + timeout_secs

  def _GetTimeRemaining():
    return end_time - time.time()

  time_remaining = _GetTimeRemaining()
  while time_remaining > 0:
    if tick:
      tick(time_remaining)
    if disable_event:
      disable_event.wait(1)
      if disable_event.is_set():
        break
    else:
      time.sleep(1)
    time_remaining = _GetTimeRemaining()
    logging.debug('time_remaining: %s', time_remaining)
  if disable_event and disable_event.is_set():
    logging.info('Timer is disabled')
    return
  timeout_handler()
