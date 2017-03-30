#!/usr/bin/python -u

# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import mock
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy
from cros.factory.goofy.plugins import plugin
from cros.factory.goofy.plugins import plugin_controller


# pylint: disable=protected-access
class PluginControllerTest(unittest.TestCase):

  BASE_PLUGIN_MODULE = 'plugin'
  BASE_PLUGIN_CLASS = 'plugin.Plugin'

  def setUp(self):
    self._goofy = mock.Mock(goofy.Goofy)

    # Load the base plugin class for test.
    self._config = {
        'backends': {self.BASE_PLUGIN_MODULE: {}}}

  def CreateController(self):
    with mock.patch('cros.factory.utils.config_utils.LoadConfig') as LoadConfig:
      LoadConfig.return_value = self._config
      controller = plugin_controller.PluginController('config', self._goofy)
      LoadConfig.assert_called_with('config', 'plugins')
      return controller

  def testInit(self):
    controller = self.CreateController()
    self.assertTrue(set(controller._plugins.keys()) == set([plugin.Plugin]))
    self._config = {
        'backends': {self.BASE_PLUGIN_CLASS: {}}}
    controller = self.CreateController()
    self.assertTrue(set(controller._plugins.keys()) == set([plugin.Plugin]))

  def testInitError(self):
    self._config['backends']['not_exist_plugin.NotExistPlugin'] = {}
    controller = self.CreateController()
    self.assertTrue(set(controller._plugins.keys()) == set([plugin.Plugin]))

  def testStartAllPlugins(self):
    mock_plugin = mock.Mock(plugin.Plugin)
    controller = self.CreateController()
    controller._plugins[type(mock_plugin)] = mock_plugin
    controller.StartAllPlugins()
    mock_plugin.Start.assert_called_with()

  def testStopAndDestroyAllPlugins(self):
    mock_plugin = mock.Mock(plugin.Plugin)
    controller = self.CreateController()
    controller._plugins[type(mock_plugin)] = mock_plugin
    controller.StopAndDestroyAllPlugins()
    mock_plugin.Stop.assert_called_with()
    mock_plugin.Destroy.assert_called_with()

  def testPauseAndResumePluginByResource(self):
    mock_plugin = mock.Mock(plugin.Plugin)
    mock_plugin.used_resources = ['TEST_RESOURCE']
    controller = self.CreateController()
    controller._plugins[type(mock_plugin)] = mock_plugin
    controller.PauseAndResumePluginByResource(set(['TEST_RESOURCE']))
    mock_plugin.Stop.assert_called_once_with()
    controller.PauseAndResumePluginByResource(set(['OTHER_RESOURCE']))
    mock_plugin.Start.assert_called_once_with()

  def testGetPluginInstance(self):
    controller = self.CreateController()
    self.assertIsNotNone(controller.GetPluginInstance(self.BASE_PLUGIN_MODULE))
    self.assertIsNone(controller.GetPluginInstance('not_exist_plugin'))

  def testGetPluginClass(self):
    self.assertEqual(plugin_controller.GetPluginClass('plugin'), plugin.Plugin)
    self.assertEqual(
        plugin_controller.GetPluginClass('plugin.Plugin'), plugin.Plugin)

  def testGetPluginRPCPath(self):
    # pylint: disable=protected-access
    self.assertEqual(
        plugin_controller._GetPluginRPCPath(
            plugin_controller.GetPluginClass('plugin')),
        '/plugin/plugin_Plugin')

  @mock.patch('cros.factory.goofy.plugins.plugin_controller.goofy_proxy')
  def testGetPluginProxy(self, goofy_proxy):
    proxy = mock.Mock()
    goofy_proxy.get_rpc_proxy.return_value = proxy
    self.assertEqual(plugin_controller.GetPluginRPCProxy('plugin'), proxy)
    goofy_proxy.get_rpc_proxy.assert_called_once_with(
        None, None, '/plugin/plugin_Plugin')
    proxy.system.listMethods.assert_called_once_with()


if __name__ == '__main__':
  unittest.main()
