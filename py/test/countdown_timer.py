# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import threading
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui

_MSG_TIME_REMAINING = lambda t: i18n_test_ui.MakeI18nLabel(
    'Time remaining: {time:.0f}', time=t)


def StartCountdownTimer(test, timeout_secs, element_id, timeout_handler=None):
  """Start a countdown timer that relies on test_ui.EventLoop.

  It updates UI for time remaining and calls timeout_handler when timeout.
  All works are done in the event loop, and no extra threads are created.

  Args:
    test: a test_ui.TestCaseWithUI instance.
    timeout_secs: (int) #seconds to timeout.
    element_id: The HTML element to place time remaining info.
    timeout_handler: (callback) called when timeout reaches.

  Returns:
    A threading.Event that would stop the countdown timer when set.
  """
  end_time = time.time() + timeout_secs
  stop_event = threading.Event()
  def _Timer():
    if stop_event.is_set():
      raise StopIteration
    time_remaining = end_time - time.time()
    if time_remaining > 0:
      test.ui.SetHTML(_MSG_TIME_REMAINING(time_remaining), id=element_id)
    else:
      if timeout_handler:
        timeout_handler()
      raise StopIteration
  test.event_loop.AddTimedHandler(_Timer, 1, repeat=True)
  return stop_event
