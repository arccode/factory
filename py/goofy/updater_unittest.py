#!/usr/bin/env python3
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import threading
import unittest
from unittest import mock

from cros.factory.goofy import updater


class CheckForUpdateTest(unittest.TestCase):

  @mock.patch('cros.factory.test.utils.update_utils.Updater')
  @mock.patch('cros.factory.test.server_proxy.GetServerProxy')
  @mock.patch('cros.factory.test.session.GetToolkitVersion')
  def _testUpdate(self, local_version, get_toolkit_version_mock=None,
                  get_server_proxy_mock=None, updater_mock=None):
    get_toolkit_version_mock.return_value = local_version

    fake_proxy = mock.MagicMock()
    get_server_proxy_mock.return_value = fake_proxy

    fake_updater = mock.MagicMock()
    fake_updater.GetUpdateVersion.return_value = '11111'
    fake_updater.IsUpdateAvailable.return_value = local_version != '11111'
    updater_mock.return_value = fake_updater

    self.assertEqual(
        updater.CheckForUpdate(3), ('11111', local_version != '11111'))

    get_toolkit_version_mock.assert_called_once_with()
    get_server_proxy_mock.assert_called_once_with(timeout=3)
    updater_mock.assert_called_once_with('toolkit', proxy=fake_proxy)
    fake_updater.GetUpdateVersion.assert_called_once_with()
    fake_updater.IsUpdateAvailable.assert_called_once_with(local_version)

  def testMustUpdate(self):
    self._testUpdate('00000')

  def testNotUpdate(self):
    self._testUpdate('11111')


class CheckForUpdateAsyncTest(unittest.TestCase):
  """Test CheckForUpdateAsync with mocked CheckForUpdate and other functions."""

  def CallbackCalled(self, *unused_args, **unused_kwargs):
    """Arguments of this function are dummy."""
    self.event.set()

  def setUp(self):
    self.event = threading.Event()
    self.event.clear()

  @mock.patch('cros.factory.goofy.updater.CheckForUpdate')
  def _testUpdate(self, available, check_for_update_mock=None):
    """Provides basic testing flow for testMustUpdate and testNotUpdate."""
    check_for_update_mock.return_value = ('11111', available)

    callback = mock.MagicMock()
    callback.side_effect = self.CallbackCalled
    updater.CheckForUpdateAsync(callback, 1)

    # In the real use case, CheckForUpdate requires a timeout. However it has
    # already been stubbed out and will return immediately in this unittest.
    # If something is wrong in CheckForUpdateAsync, we will wait for
    # at most 1 second and verify its correctness.

    self.event.wait(1)

    check_for_update_mock.assert_called_once_with(timeout=1)
    callback.assert_called_once_with(True, '11111', available)

  def testMustUpdate(self):
    self._testUpdate(True)

  def testNotUpdate(self):
    self._testUpdate(False)

  @mock.patch('cros.factory.goofy.updater.CheckForUpdate')
  def testCanNotReach(self, check_for_update_mock):
    check_for_update_mock.side_effect = Exception(
        'Can not contact factory server')
    callback = mock.MagicMock()
    callback.side_effect = self.CallbackCalled

    updater.CheckForUpdateAsync(callback, 1)

    # See comments in _testUpdate for the explanation of event waiting.

    self.event.wait(1)

    check_for_update_mock.assert_called_once_with(timeout=1)
    callback.assert_called_once_with(False, None, False)


if __name__ == '__main__':
  unittest.main()
