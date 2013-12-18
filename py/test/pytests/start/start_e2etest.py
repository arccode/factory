# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An E2E test to test the start factory test."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.e2e_test import e2e_test

class StartE2ETest(e2e_test.E2ETest):
  """The start E2E test."""
  pytest_name = 'start'
  dargs = dict(
      press_to_continue=True,
      require_external_power=False,
      check_factory_install_complete=False)

  @e2e_test.E2ETestCase()
  def testPressSpace(self):
    # Wait for the instruction on UI to show.
    self.uictl.WaitForContent(search_text='Hit SPACE to start testing')
    # Press SPACE key.
    self.uictl.PressKey(self.uictl.KEY_SPACE)
    # Wait to verify that the test passes.
    self.WaitForPass(msg='Timeout waiting for space key')

  @e2e_test.E2ETestCase()
  def testPressSpaceIdle(self):
    self.uictl.WaitForContent(search_text='Hit SPACE to start testing')
    # Make sure the test stays active.
    self.WaitForActive(msg='Test finished without pressing space key')

  @e2e_test.E2ETestCase(dargs=dict(press_to_continue=False))
  def testNoPressSpace(self):
    self.WaitForPass()
