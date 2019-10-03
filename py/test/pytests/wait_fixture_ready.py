# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Waits Fixture until it's ready.

Description
-----------
This test will try to set up a connection to the given fixture, when the
connection is established, the test will pass.  Otherwise, it will keep
retrying.

DEPENDENCY
----------
Depends on how to connect to the fixture, it can be SSH or ADB or something
else.
"""

from cros.factory.test.fixture import bft_fixture
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


_CHECK_INTERVAL_SECS = 0.2


class WaitBFTReady(test_case.TestCase):
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
  ]

  def runTest(self):
    self.ui.SetState('Wait Fixture Ready...')

    while True:
      try:
        # The following line will setup the connect to BFT fixture, so if it can
        # be done without exception, the fixture should be ready.
        bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
      except bft_fixture.BFTFixtureException:
        self.Sleep(_CHECK_INTERVAL_SECS)
      else:
        break
