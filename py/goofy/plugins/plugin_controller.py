# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os

from jsonrpclib import ProtocolError

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import goofy_proxy
from cros.factory.test.env import paths
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


# PRC URL prefix used by plugin.
PLUGIN_PREFIX = '/plugin'


def _GetPluginRPCPath(plugin_path):
  """Returns the RPC path that should be used by a given plugin path.

  The input argument should be the full path of the plugin class *after*
  `cros.factory.goofy.plugins`.
  """
  subpath = plugin_path.replace('.', '_')
  return '%s/%s' % (PLUGIN_PREFIX, subpath)


def GetPluginRPCProxy(plugin_name, address=None, port=None):
  """Returns the RPC proxy of a plugin.

  Returns None if no such plugin running in goofy.
  """
  plugin_class = plugin.GetPluginClass(plugin_name)
  if plugin_class is None:
    return None

  proxy = goofy_proxy.GetRPCProxy(
      address, port,
      _GetPluginRPCPath(plugin.GetPluginNameFromClass(plugin_class)))
  try:
    # Try listing methods to check if the path exists.
    proxy.system.listMethods()
    return proxy
  except ProtocolError as err:
    # ProtocolError has many different cases, and it may has a nested tuple.
    if 404 in type_utils.FlattenTuple(err.args):
      # The requested plugin is not running
      logging.debug('The requested plugin %s is not running', plugin_name)
      return None
    else:
      raise


class PluginController(object):
  """Controller of Goofy plugins."""

  def __init__(self, config_name, goofy):
    """Constructor

    Args:
      config_name: the name of the config to be loaded for plugins.
      goofy: the goofy instance.
    """
    self._plugins = {}
    self._menu_items = {}
    self._frontend_configs = []

    plugin_config = config_utils.LoadConfig('goofy_plugins', 'plugins')
    config_utils.OverrideConfig(
        plugin_config, config_utils.LoadConfig(config_name, 'plugins'))

    for name, plugin_args in plugin_config['plugins'].iteritems():
      if not plugin_args.get('enabled', True):
        logging.debug('Plugin disabled: %s', name)
        continue
      args = plugin_args.get('args', {})
      args['goofy'] = goofy
      plugin_class = plugin.GetPluginClass(name)
      if plugin_class:
        try:
          plugin_instance = plugin_class(**args)
          plugin_name = plugin.GetPluginNameFromClass(plugin_class)

          self._plugins[plugin_name] = plugin_instance
        except Exception:
          logging.exception('Failed to load plugin: %s', name)
      else:
        logging.error('Failed to load plugin class: %s', name)

    self._RegisterMenuItem()
    self._RegisterRPC(goofy.goofy_server)
    self._RegisterFrontendPath(goofy.goofy_server)

  def _RegisterMenuItem(self):
    """Registers plugins' menu items."""
    for name, instance in self._plugins.iteritems():
      try:
        for menu_item in instance.GetMenuItems():
          self._menu_items[menu_item.id] = menu_item
      except Exception:
        logging.exception('Failed to get menu items from %s', name)

  def _RegisterFrontendPath(self, goofy_server):
    base = os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR, 'goofy', 'plugins')
    for name, instance in self._plugins.iteritems():
      plugin_paths = name.split('.')
      if len(plugin_paths) < 2:
        continue

      dirname = os.path.join(*plugin_paths[:-1])
      full_file_path = os.path.join(base, dirname, 'static')

      if not os.path.exists(full_file_path):
        continue

      url_base_path = _GetPluginRPCPath(name)
      goofy_server.RegisterPath(url_base_path, full_file_path)

      try:
        location = instance.GetUILocation()
        if not location:
          continue
        if location is True:
          location = 'testlist'
        self._frontend_configs.append({
            'url': '%s/%s.html' % (url_base_path, plugin_paths[-1]),
            'location': location
        })
      except Exception:
        logging.exception('Failed to check GetUILocation from %s.', name)


  def StartAllPlugins(self):
    """Starts all plugins."""
    for plugin_instance in self._plugins.values():
      plugin_instance.Start()

  def _RegisterRPC(self, goofy_server):
    """Registers plugins to Goofy server."""
    for plugin_path, plugin_instance in self._plugins.iteritems():
      rpc_instance = plugin_instance.GetRPCInstance()
      if rpc_instance is not None:
        goofy_server.AddRPCInstance(
            _GetPluginRPCPath(plugin_path), rpc_instance)

  def StopAndDestroyAllPlugins(self):
    """Stops and destroys all plugins."""
    for plugin_instance in self._plugins.values():
      plugin_instance.Stop()
      plugin_instance.Destroy()

  def PauseAndResumePluginByResource(self, exclusive_resources):
    """Pauses or resumes plugin based on the resources.

    Given the resources that current tests required to use exclusively, pause
    the corresponding plugins and resume other plugins.

    Args:
      exclusive_resources: A set of resources used by current tests exclusively.
    """
    for plugin_instance in self._plugins.values():
      if exclusive_resources.intersection(set(plugin_instance.used_resources)):
        plugin_instance.Stop()
      else:
        plugin_instance.Start()

  def GetPluginInstance(self, plugin_name):
    """Returns the plugin instance.

    Returns the plugin instance, or None if no plugin found.
    """
    plugin_class = plugin.GetPluginClass(plugin_name)
    if not plugin_class:
      return None
    return self._plugins.get(plugin.GetPluginNameFromClass(plugin_class))

  def GetPluginMenuItems(self):
    """Returns a list all plugins menu items."""
    return self._menu_items.values()

  def GetFrontendConfigs(self):
    """Returns a list of configs of all plugin's UI."""
    return self._frontend_configs

  def OnMenuItemClicked(self, item_id):
    """Called when a plugin menu item is clicked."""
    return self._menu_items[item_id].callback()
