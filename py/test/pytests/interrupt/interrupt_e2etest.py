# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An E2E test to test the interrupt factory test."""

# pylint: disable=C0322

import mock

import factory_common  # pylint: disable=W0611
from cros.factory.test.e2e_test import e2e_test
from cros.factory.test.pytests.interrupt import interrupt


class InterruptE2ETest(e2e_test.E2ETest):
  """The interrupt E2E test."""
  pytest_name = 'interrupt'

  @e2e_test.E2ETestCase(dargs=dict(interrupt=88))
  @mock.patch.object(interrupt.sys_utils, 'GetInterrupts',
                     return_value={'88': 100})
  def testPass(self, mock_GetInterrupts):
    self.WaitForPass()
    mock_GetInterrupts.assert_called_once()

  @e2e_test.E2ETestCase(dargs=dict(interrupt=66))
  @mock.patch.object(interrupt.sys_utils, 'GetInterrupts',
                     return_value={'66': 0})
  def testFail(self, mock_GetInterrupts):
    self.WaitForFail()
    mock_GetInterrupts.assert_called_once()
