# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# This test case is a manual test to do audio functions on DUT
# and let operator or engineer mark pass or fail from their own judgement.

import unittest

from cros.factory.test import test_ui

class AudioDiagnosticTest(unittest.TestCase):
  """A test executing audio diagnostic tools.

  This is a manual test run by operator who judges
  pass/fail result according to the heard audio quality.
  """

  def setUp(self):
    """
    Initializes the UI displaying diagnostic controls
    and bind events to corresponding tasks at backend.
    """
    self._ui = test_ui.UI()
    self._ui.AddEventHandler('fail', self.Fail)
    self._ui.AddEventHandler('pass', self.Pass)

  def Fail(self, event): # pylint:disable=W0613
    self._ui.Fail('Fail with bad audio quality')

  def Pass(self, event): # pylint:disable=W0613
    self._ui.Pass()

  def runTest(self):
    self._ui.Run()
