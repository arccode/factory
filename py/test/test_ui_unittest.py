#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for TestUI module."""

from __future__ import print_function

import mock
import os
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory.test import event
from cros.factory.test import factory
from cros.factory.test import test_ui


class TestUIUnittest(unittest.TestCase):
  """Unit tests for TestUI."""

  def setUp(self):
    self.test_path = 'test.path'
    self.invocation = 'test_invocation'
    self.parent_invocation = 'parent_invocation'

    os.environ['CROS_FACTORY_TEST_PATH'] = self.test_path
    os.environ['CROS_FACTORY_TEST_INVOCATION'] = self.invocation
    os.environ['CROS_FACTORY_TEST_PARENT_INVOCATION'] = self.parent_invocation

    self.event_client_patcher = mock.patch.object(test_ui, 'EventClient',
                                                  auto_spec=True)
    self.mock_event_client = self.event_client_patcher.start()

  def tearDown(self):
    self.event_client_patcher.stop()

  def testUIException(self):
    # Create a mock UI abort event.
    ui_abort_event = mock.Mock()
    ui_abort_event.type = event.Event.Type.END_TEST
    ui_abort_event.invocation = self.invocation
    ui_abort_event.test = self.test_path
    ui_abort_event.status = factory.TestState.FAILED
    ui_abort_event.error_msg = 'Aborted by operator'

    # Blocking mode. The UI main thread should exit when it sees the failed
    # event.
    ui = test_ui.UI()
    ui.event_client.wait = mock.Mock(return_value=ui_abort_event)
    self.assertRaisesRegexp(
        factory.FactoryTestFailure, r'Aborted by operator',
        ui.Run, blocking=True)

    # Non-blocking mode. The UI main thread should be terminated by a SIGINT.
    ui = test_ui.UI()
    ui.event_client.wait = mock.Mock(return_value=ui_abort_event)
    self.assertRaisesRegexp(
        factory.FactoryTestFailure, r'Test aborted by SIGINT',
        ui.Run, blocking=False)


if __name__ == '__main__':
  unittest.main()
