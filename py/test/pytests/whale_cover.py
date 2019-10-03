# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks if Whale's cover is opened / closed."""

import logging

from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


class WhaleCoverTest(test_case.TestCase):
  """Checks if Whale's cover is opened / closed."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('check_interval_secs', (int, float),
          'Interval of checking cover', default=0.5),
      Arg('check_open', bool,
          "True to check if the cover is open; False to check if it's closed",
          default=True),
  ]

  def CheckCoverStatus(self):
    """Checks the cover until it's open or closed."""
    if self.args.check_open:
      hint = _('Please open the cover!')
      expect_status = self._bft.Status.OPEN
    else:
      hint = _('Please close the cover!')
      expect_status = self._bft.Status.CLOSED

    done = False
    try:
      while not done:
        done = self._bft.CoverStatus() == expect_status
        if not done:
          self.ui.SetState(hint)
          self.Sleep(self.args.check_interval_secs)
    except Exception:
      logging.exception('Failed to check cover status')
      self.FailTask('Failed to check cover status')

    self.PassTask()

  def setUp(self):
    self._bft = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

  def runTest(self):
    self.ui.SetState(_('Checking The Cover'))
    self.CheckCoverStatus()
