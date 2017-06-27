# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An E2E test to test the shutdown factory test."""

from __future__ import print_function

import mock
import re
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test import e2e_test
from cros.factory.test import factory
from cros.factory.test.pytests.shutdown import shutdown
from cros.factory.test import state


# Goofy RPC mock.
_goofy = mock.MagicMock()

# Event client mock.
_event_client = mock.MagicMock()
mock_event_client_instance = mock.Mock()
_event_client.__enter__ = mock.Mock(return_value=mock_event_client_instance)

_VALID_POST_SHUTDOWN_DATA = {
    'invocation': 'abc',
    'goofy_error': None}


class RegExpMatcher(object):
  """A regular expression matcher to be used in function call assertion.

  Args:
    regexp: The regular expression to search in a given string.
  """

  def __init__(self, regexp):
    self.regexp = re.compile(regexp)

  def __eq__(self, other):
    return bool(self.regexp.search(other))


class ShutdownE2ETest(e2e_test.E2ETest):
  """The shutdown E2E test"""
  pytest_name = 'shutdown'
  dargs = dict(
      operation='reboot')

  def setUp(self):
    self.key_post_shutdown = state.KEY_POST_SHUTDOWN % self.test_info.path

  @e2e_test.E2ETestCase()
  @mock.patch.object(state, 'get_instance',
                     return_value=_goofy)
  @mock.patch.object(shutdown, 'EventClient',
                     return_value=_event_client)
  def testReboot(self, mock_event_client, mock_get_state_instance):
    # Set 'post_shutdown' to None.
    _goofy.get_shared_data = mock.Mock(return_value=None)
    # No one aborts shutdown.
    mock_event_client_instance.wait = mock.Mock(return_value=None)

    self.WaitForActive()

    mock_get_state_instance.assert_called_with()
    mock_event_client.assert_called_with()
    _goofy.get_shared_data.assert_called_with(self.key_post_shutdown, True)
    _goofy.Shutdown.assert_called_with('reboot')

  @e2e_test.E2ETestCase()
  @mock.patch.object(state, 'get_instance',
                     return_value=_goofy)
  @mock.patch.object(shutdown, 'EventClient',
                     return_value=_event_client)
  def testRebootAborted(self, mock_event_client, mock_get_state_instance):
    # Set 'post_shutdown' to None.
    _goofy.get_shared_data = mock.Mock(return_value=None)
    # Operator aborts shutdown.
    mock_event_client_instance.wait = mock.Mock(return_value=False)

    self.WaitForFail()

    mock_get_state_instance.assert_called_with()
    mock_event_client.assert_called_with()
    _goofy.get_shared_data.assert_called_with(self.key_post_shutdown, True)

  @e2e_test.E2ETestCase()
  @mock.patch.object(state, 'get_state_instance',
                     return_value=_goofy)
  @mock.patch.object(shutdown.event_log, 'Log')
  def testPostShutdown(self, mock_log, mock_get_state_instance):
    # Set 'post_shutdown' to success reboot state.
    _goofy.get_shared_data = mock.Mock(
        return_value=_VALID_POST_SHUTDOWN_DATA)
    # Fake a reasonable shutdown time.
    _goofy.GetLastShutdownTime = mock.Mock(return_value=(time.time() - 5))

    self.WaitForPass()

    mock_get_state_instance.assert_called_with()
    mock_log.assert_called_with('rebooted',
                                duration=mock.ANY,
                                status=factory.TestState.PASSED,
                                error_msg=None)
    _goofy.get_shared_data.assert_called_with(self.key_post_shutdown, True)
    _goofy.del_shared_data.assert_called_with(self.key_post_shutdown)

  @e2e_test.E2ETestCase()
  @mock.patch.object(state, 'get_instance',
                     return_value=_goofy)
  @mock.patch.object(shutdown.event_log, 'Log')
  def testNoShutdownTime(self, mock_log, mock_get_state_instance):
    # Set 'post_shutdown' to success reboot state.
    _goofy.get_shared_data = mock.Mock(
        return_value=_VALID_POST_SHUTDOWN_DATA)
    # No shutdown time was recorded.
    _goofy.GetLastShutdownTime = mock.Mock(return_value=None)

    self.WaitForFail()

    mock_get_state_instance.assert_called_with()
    mock_log.assert_called_with(
        'rebooted', status=factory.TestState.FAILED,
        error_msg=('Unable to read shutdown_time; '
                   'unexpected shutdown during reboot?'))
    _goofy.get_shared_data.assert_called_with(self.key_post_shutdown, True)
    _goofy.del_shared_data.assert_called_with(self.key_post_shutdown)

  @e2e_test.E2ETestCase()
  @mock.patch.object(state, 'get_state_instance',
                     return_value=_goofy)
  @mock.patch.object(shutdown.event_log, 'Log')
  def testClockMovingBackward(self, mock_log, mock_get_state_instance):
    # Set 'post_shutdown' to success reboot state.
    _goofy.get_shared_data = mock.Mock(
        return_value=_VALID_POST_SHUTDOWN_DATA)
    # Set a future shutdown time to simulate RTC moving backward.
    _goofy.GetLastShutdownTime = mock.Mock(return_value=(time.time() + 100))

    self.WaitForFail()

    mock_get_state_instance.assert_called_with()
    mock_log.assert_called_with('rebooted',
                                status=factory.TestState.FAILED,
                                error_msg='Time moved backward during reboot')
    _goofy.get_shared_data.assert_called_with(self.key_post_shutdown, True)
    _goofy.del_shared_data.assert_called_with(self.key_post_shutdown)

  @e2e_test.E2ETestCase(dargs={'max_reboot_time_secs': 10})
  @mock.patch.object(state, 'get_instance',
                     return_value=_goofy)
  @mock.patch.object(shutdown.event_log, 'Log')
  def testRebootTakeTooLong(self, mock_log, mock_get_state_instance):
    # Set 'post_shutdown' to success reboot state.
    _goofy.get_shared_data = mock.Mock(
        return_value=_VALID_POST_SHUTDOWN_DATA)
    # Reboot took 100 seconds.
    _goofy.GetLastShutdownTime = mock.Mock(return_value=(time.time() - 100))

    self.WaitForFail()

    mock_get_state_instance.assert_called_with()
    mock_log.assert_called_with('rebooted',
                                duration=mock.ANY,
                                status=factory.TestState.FAILED,
                                error_msg=RegExpMatcher(
                                    r'More than \d+ s elapsed during reboot'))
    _goofy.get_shared_data.assert_called_with(self.key_post_shutdown, True)
    _goofy.del_shared_data.assert_called_with(self.key_post_shutdown)
