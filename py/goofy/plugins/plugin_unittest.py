#!/usr/bin/python -u

# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import mock
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy
from cros.factory.goofy.plugins import plugin


class PluginTest(unittest.TestCase):

  def setUp(self):
    self._plugin = plugin.Plugin(mock.Mock(goofy.Goofy))
    self._plugin.OnStart = mock.Mock()
    self._plugin.OnStop = mock.Mock()
    self._plugin.OnDestroy = mock.Mock()

  def testStart(self):
    self._plugin.Start()
    self._plugin.OnStart.assert_called_once_with()

    # If a plugin is started, calling Start() should not run OnStart again.
    self._plugin.OnStart.reset_mock()
    self._plugin.Start()
    self._plugin.OnStart.assert_not_called()

  def testStop(self):
    # If a plugin is not started, calling Stop() should not run OnStop.
    self._plugin.Stop()
    self._plugin.OnStop.assert_not_called()

    # Normal case, start and stop.
    self._plugin.Start()
    self._plugin.Stop()
    self._plugin.OnStop.assert_called_once_with()

    # If a plugin is stopped, calling Stop() again should not run OnStop again.
    self._plugin.OnStop.reset_mock()
    self._plugin.Stop()
    self._plugin.OnStop.assert_not_called()

  def testDestroy(self):
    self._plugin.Start()
    self._plugin.Destroy()

    # Make sure OnStop and OnDestroy are called.
    # self._plugin.OnStop.assert_called_once_with()
    self._plugin.OnDestroy.assert_called_once_with()

    # If a plugin is destroyed, calling Destroy() again should not run
    # OnDestroy again.
    self._plugin.OnDestroy.reset_mock()
    self._plugin.Destroy()
    self._plugin.OnDestroy.assert_not_called()

  def testError(self):
    """Make sure exceptions in OnXXX function won't crash it's user."""
    def ErrorFunction():
      raise RuntimeError

    self._plugin.OnStart = ErrorFunction
    self._plugin.OnStop = ErrorFunction
    self._plugin.OnDestroy = ErrorFunction
    self._plugin.Start()
    self._plugin.Stop()
    self._plugin.Destroy()


if __name__ == '__main__':
  unittest.main()
