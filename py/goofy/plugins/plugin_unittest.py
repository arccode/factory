#!/usr/bin/env python2

# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import mock

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

  def testGetRPCInstance(self):

    # The basic class to be tested, also try to access data member to make sure
    # the function is bound to the correct instance.
    class PluginA(plugin.Plugin):
      def __init__(self, goofy_instance):
        super(PluginA, self).__init__(goofy_instance)
        self.data_a = 1
        self.data_b = 2

      @plugin.RPCFunction
      def A(self):
        return self.data_a

      @plugin.RPCFunction
      def B(self):
        return self.data_b

    # Another class to be tested with the same function name as PluginA. This
    # is to ensure functions between classes won't be overrided.
    class PluginB(plugin.Plugin):
      def __init__(self, goofy_instance):
        super(PluginB, self).__init__(goofy_instance)
        self.data_a = 3
        self.data_b = 4

      @plugin.RPCFunction
      def A(self):
        return self.data_a

      @plugin.RPCFunction
      def B(self):
        return self.data_b

    # Make sure inheritance also works.
    class PluginC(PluginA):
      @plugin.RPCFunction
      def A(self):
        return 3

    classes = [PluginA, PluginB, PluginC]
    plugins = []
    for cls in classes:
      plugins.append(cls(mock.Mock(goofy.Goofy)))

    rpc_instances = []
    for p in plugins:
      rpc_instances.append(p.GetRPCInstance())

    expected_value = [[1, 2], [3, 4], [3, 2]]
    for idx, rpc_instance in enumerate(rpc_instances):
      self.assertItemsEqual(rpc_instance.__dict__.keys(), ['A', 'B'])
      self.assertEqual(rpc_instance.A(), expected_value[idx][0])
      self.assertEqual(rpc_instance.B(), expected_value[idx][1])

  def testGetPluginClass(self):
    self.assertEqual(plugin.GetPluginClass('plugin'), plugin.Plugin)
    self.assertEqual(plugin.GetPluginClass('plugin.Plugin'), plugin.Plugin)

  def testGetPluginPathFromClass(self):
    self.assertEqual(
        plugin.GetPluginNameFromClass(plugin.GetPluginClass('plugin')),
        'plugin')

if __name__ == '__main__':
  unittest.main()
