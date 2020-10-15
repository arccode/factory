# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""WebGL performance test that executes a set of WebGL operations."""

import time

from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


class WebGLAquariumTest(test_case.TestCase):
  ARGS = [
      Arg('duration_secs', int, 'Duration of time in seconds to run the test',
          default=60),
      Arg('hide_options', bool, 'Whether to hide the options on UI',
          default=True),
      Arg('full_screen', bool, 'Whether to go full screen mode by default',
          default=True)
  ]

  def setUp(self):
    self.end_time = time.time() + self.args.duration_secs

    if self.args.full_screen:
      self.ui.CallJSFunction('toggleFullScreen')

  def FormatSeconds(self, secs):
    hours = int(secs / 3600)
    minutes = int((secs / 60) % 60)
    seconds = int(secs % 60)
    return '%02d:%02d:%02d' % (hours, minutes, seconds)

  def PeriodicCheck(self):
    time_left = self.end_time - time.time()
    if time_left <= 0:
      self.PassTask()
    self.ui.CallJSFunction(
        'updateUI', self.FormatSeconds(time_left),
        self.args.hide_options)

  def runTest(self):
    self.event_loop.AddTimedHandler(self.PeriodicCheck, 1, repeat=True)
    self.WaitTaskEnd()
