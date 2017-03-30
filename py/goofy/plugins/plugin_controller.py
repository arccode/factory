# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import inspect
import logging
from xmlrpclib import ProtocolError

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import goofy_proxy
from cros.factory.utils import config_utils


# PRC URL prefix used by plugin.
PLUGIN_PREFIX = '/plugin'


# Base package name of Goofy plugins."""
_PLUGIN_MODULE_BASE = 'cros.factory.goofy.plugins'


def GetPluginClass(plugin_name):
  """Returns the class of the plugin.

  This function searches `cros.factory.goofy.plugins.{plugin_name}`.

  If a module name is provided, the module should contain only one class that
  is derived from `cros.factory.goofy.plugins.plugin.Plugin`, and the class
  would be returned by this function.

  For example, if `plugin_name` is 'time_sanitizer',
  class `cros.factory.goofy.plugins.time_sanitizer.TimeSanitizer` is returned.

  If a class name is provided, the class would be returned.
  For example, `plugin_name` can be 'time_sanitizer.TimeSanitizer'

  Args:
    plugin_name: the class or module name of the plugin under
        `cros.factory.goofy.plugins`
  """
  full_name = '.'.join([_PLUGIN_MODULE_BASE, plugin_name])
  prefix, target_name = full_name.rsplit('.', 1)
  target_name = str(target_name)  # Convert from unicode.
  try:
    target = getattr(__import__(prefix, fromlist=[target_name]), target_name)
  except Exception:
    logging.exception('Failed to import %s', plugin_name)
    return None

  if inspect.isclass(target):
    return target
  else:
    target_class = None
    for obj in inspect.getmembers(target):
      if (inspect.isclass(obj[1]) and
          obj[1].__module__ == full_name and
          issubclass(obj[1], plugin.Plugin)):
        assert target_class is None, (
            'Multiple plugins class found in %s' % plugin_name)
        target_class = obj[1]
    return target_class


def _GetPluginRPCPath(plugin_class):
  """Returns the RPC path that should be used by a given plugin class"""
  subpath = '%s.%s' % (plugin_class.__module__, plugin_class.__name__)
  subpath = subpath[len(_PLUGIN_MODULE_BASE) + 1:]
  subpath = subpath.replace('.', '_')
  return "%s/%s" % (PLUGIN_PREFIX, subpath)


def GetPluginRPCProxy(plugin_name, address=None, port=None):
  """Returns the PRC proxy of a plugin.

  Returns None if no such plugin running in goofy.
  """
  proxy = goofy_proxy.get_rpc_proxy(
      address, port, _GetPluginRPCPath(GetPluginClass(plugin_name)))
  try:
    # Try listing methods to check if the path exists.
    proxy.system.listMethods()
    return proxy
  except ProtocolError as error:
    if error.errcode == 404:
      # The requested plugin is not running
      logging.debug('The requested plugin %s is not running', plugin_name)
      return None
    else:
      raise error


class PluginController(object):
  """Controller of Goofy plugins."""

  def __init__(self, config_name, goofy):
    """Constructor

    Args:
      config_name: the name of the config to be loaded for plugins.
      goofy: the goofy instance.
    """
    self._plugins = {}

    plugin_config = config_utils.LoadConfig(
        config_name, 'plugins')

    for name, plugin_args in plugin_config['backends'].iteritems():
      args = plugin_args.get('args', {})
      args['goofy'] = goofy
      plugin_class = GetPluginClass(name)
      if plugin_class:
        try:
          self._plugins[plugin_class] = plugin_class(**args)
        except Exception as error:
          logging.error('Failed to load plugin: %s', name)
          logging.exception(error)
      else:
        logging.error('Failed to load plugin class: %s', name)

  def StartAllPlugins(self):
    """Starts all plugins."""
    for plugin_instance in self._plugins.values():
      plugin_instance.Start()

  def RegisterRPC(self, goofy_server):
    """Registers plugins to Goofy server."""
    for plugin_class, plugin_instance in self._plugins.iteritems():
      rpc_instance = plugin_instance.GetRPCInstance()
      if rpc_instance is not None:
        goofy_server.AddRPCInstance(
            _GetPluginRPCPath(plugin_class), rpc_instance)

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
    plugin_class = GetPluginClass(plugin_name)
    return self._plugins.get(plugin_class) if plugin_class else None
