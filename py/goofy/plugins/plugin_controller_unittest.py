#!/usr/bin/env python2

# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy
from cros.factory.goofy import goofy_server
from cros.factory.goofy.plugins import plugin
from cros.factory.goofy.plugins import plugin_controller
from cros.factory.test.env import paths


# pylint: disable=protected-access
class PluginControllerTest(unittest.TestCase):

  BASE_PLUGIN_MODULE = 'mock_plugin.mock_plugin'

  def setUp(self):
    self._goofy = mock.Mock(goofy.Goofy)
    self._goofy.goofy_server = mock.Mock(goofy_server.GoofyServer)

    # Load the base plugin class for test.
    self._config = {'plugins': {self.BASE_PLUGIN_MODULE: {}}}

  def CreateController(self):
    with mock.patch('cros.factory.utils.config_utils.LoadConfig') as LoadConfig:
      LoadConfig.return_value = self._config
      controller = plugin_controller.PluginController('config', self._goofy)
      LoadConfig.assert_called_with('config', 'plugins')
      return controller

  def testInit(self):
    controller = self.CreateController()
    self.assertItemsEqual(controller._plugins.keys(), [self.BASE_PLUGIN_MODULE])
    self.assertItemsEqual(controller._frontend_configs, [{
        'url': '/plugin/mock_plugin_mock_plugin/mock_plugin.html',
        'location': 'testlist'
    }])
    self._goofy.goofy_server.RegisterPath.assert_called_once_with(
        '/plugin/mock_plugin_mock_plugin',
        os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR,
                     'goofy', 'plugins', 'mock_plugin', 'static'))

  def testInitError(self):
    self._config['plugins']['not_exist_plugin.NotExistPlugin'] = {}
    controller = self.CreateController()
    self.assertItemsEqual(controller._plugins.keys(), [self.BASE_PLUGIN_MODULE])

  def testStartAllPlugins(self):
    mock_plugin = mock.Mock(plugin.Plugin)
    controller = self.CreateController()
    controller._plugins['mock_plugin.MockPlugin'] = mock_plugin
    controller.StartAllPlugins()
    mock_plugin.Start.assert_called_with()

  def testStopAndDestroyAllPlugins(self):
    mock_plugin = mock.Mock(plugin.Plugin)
    controller = self.CreateController()
    controller._plugins['mock_plugin.MockPlugin'] = mock_plugin
    controller.StopAndDestroyAllPlugins()
    mock_plugin.Stop.assert_called_with()
    mock_plugin.Destroy.assert_called_with()

  def testPauseAndResumePluginByResource(self):
    mock_plugin = mock.Mock(plugin.Plugin)
    mock_plugin.used_resources = ['TEST_RESOURCE']
    controller = self.CreateController()
    controller._plugins['mock_plugin.MockPlugin'] = mock_plugin
    controller.PauseAndResumePluginByResource(set(['TEST_RESOURCE']))
    mock_plugin.Stop.assert_called_once_with()
    controller.PauseAndResumePluginByResource(set(['OTHER_RESOURCE']))
    mock_plugin.Start.assert_called_once_with()

  def testGetPluginInstance(self):
    controller = self.CreateController()
    self.assertIsNotNone(controller.GetPluginInstance(self.BASE_PLUGIN_MODULE))
    self.assertIsNone(controller.GetPluginInstance('not_exist_plugin'))

  def testGetPluginRPCPath(self):
    # pylint: disable=protected-access
    self.assertEqual(
        plugin_controller._GetPluginRPCPath('plugin'), '/plugin/plugin')

  @mock.patch('cros.factory.goofy.plugins.plugin_controller.goofy_proxy')
  def testGetPluginProxy(self, goofy_proxy):
    proxy = mock.Mock()
    goofy_proxy.GetRPCProxy.return_value = proxy
    self.assertEqual(plugin_controller.GetPluginRPCProxy('plugin'), proxy)
    goofy_proxy.GetRPCProxy.assert_called_once_with(
        None, None, '/plugin/plugin')
    proxy.system.listMethods.assert_called_once_with()

  def testOnMenuItemClicked(self):
    controller = self.CreateController()
    mock_callback = mock.Mock()
    item = plugin.MenuItem('test', mock_callback)
    controller._menu_items[item.id] = item
    controller.OnMenuItemClicked(item.id)
    mock_callback.assert_called_once_with()

  def testGetPluginMenuItems(self):
    controller = self.CreateController()
    item = plugin.MenuItem('test', None)
    controller._menu_items[item.id] = item
    self.assertEqual([item], controller.GetPluginMenuItems())

  def testGetFrontendConfigs(self):
    controller = self.CreateController()
    url = '/plugin/mock_plugin_mock_plugin/mock_plugin.html'
    config = {'url': url, 'location': 'testlist'}
    controller._frontend_configs = [config]
    self.assertEqual([config], controller.GetFrontendConfigs())

if __name__ == '__main__':
  unittest.main()
