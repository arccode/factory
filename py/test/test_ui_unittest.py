#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for TestUI module."""

from __future__ import print_function

import os
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.utils import type_utils


class TestUIUnittest(unittest.TestCase):
  """Unit tests for TestUI."""

  def setUp(self):
    self.test_path = 'test.path'
    self.invocation = 'test_invocation'

    os.environ[session.ENV_TEST_PATH] = self.test_path
    os.environ[session.ENV_TEST_INVOCATION] = self.invocation

    self.event_client_patcher = mock.patch.object(event, 'BlockingEventClient',
                                                  autospec=True)
    self.mock_event_client = self.event_client_patcher.start()

  def tearDown(self):
    self.event_client_patcher.stop()

  def testUIException(self):
    # Create a mock UI abort event.
    ui_abort_event = mock.Mock()
    ui_abort_event.type = event.Event.Type.END_TEST
    ui_abort_event.invocation = self.invocation
    ui_abort_event.test = self.test_path
    ui_abort_event.status = state.TestState.FAILED
    ui_abort_event.error_msg = 'Aborted by operator'

    # The UI main thread should exit when it sees the failed event.
    ui = test_ui.UI()
    ui.event_client.wait = mock.Mock(return_value=ui_abort_event)
    self.assertRaisesRegexp(
        type_utils.TestFailure, r'Aborted by operator',
        ui.Run)


if __name__ == '__main__':
  unittest.main()
