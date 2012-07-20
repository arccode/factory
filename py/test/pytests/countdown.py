# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A count down UI for run-in test.

It only shows count down and system loads for run-in period.

Test parameter:
  duration_secs: Number of seconds to count down.
'''

import time
import unittest

from cros.factory.test import test_ui


class CountDownTest(unittest.TestCase):
  def UpdateTimeAndLoad(self):
    self._ui.SetHTML(
        time.strftime('%H:%M:%S', time.gmtime(self._elapsed_secs)),
        id='elapsed-time')
    self._ui.SetHTML(
        time.strftime('%H:%M:%S', time.gmtime(self._remaining_secs)),
        id='remaining-time')
    self._ui.SetHTML(
        ' '.join(open('/proc/loadavg').read().split()[0:3]),
        id='system-load')

  def runTest(self):
    self._ui = test_ui.UI()
    self._duration_secs = self.test_info.args['duration_secs']
    self._start_secs = time.time()
    self._elapsed_secs = 0
    self._remaining_secs = self._duration_secs

    # Loop until count-down ends.
    while self._remaining_secs >= 0:
      self.UpdateTimeAndLoad()
      time.sleep(1)
      self._elapsed_secs = time.time() - self._start_secs
      self._remaining_secs = round(self._duration_secs - self._elapsed_secs)
