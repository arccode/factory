#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


class DUTHooks(component.DUTComponent):
  """Utility class managing device-specific callbacks."""

  def OnTestStart(self):
    """Callback invoked when factory test starts.

    This method is called when goofy starts or when the operator
    starts a test manually. This can be used to light up a green
    LED or send a notification to a remote server.
    """
    pass

  def OnTestFailure(self, test):
    """Callback invoked when a test fails.

    This method can be used to bring the attention of the operators
    when a display is not available. For example, lightting up a red
    LED may help operators identify failing device on the run-in
    rack easily.
    """
    pass

  def OnSummaryGood(self):
    """Callback invoked when the test summary page shows and all test passed.

    This method can be used to notify the operator that a device has finished
    a test section, e.g. run-in. For example, lightting up a green LED here
    and the operators may be instructed to move all devices with a green LED
    to FATP testing.
    """
    pass

  def OnSummaryBad(self):
    """Callback invoked when the test summary page shows and some test failed.

    Similar to OnSummaryGood, but is used to notify the operator of failing
    test(s).
    """
    pass
