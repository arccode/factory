# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import inspect
import logging
import uuid

from cros.factory.utils import debug_utils
from cros.factory.utils import type_utils


# Type of resources that can be used by plugins.
RESOURCE = type_utils.Enum([
    'CPU',
    'LED',
    'NETWORK',
    'POWER'
])

# Base package name of Goofy plugins.
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
  target_class = None
  for unused_name, obj in inspect.getmembers(target):
    if (inspect.isclass(obj) and
        obj.__module__ == full_name and
        issubclass(obj, Plugin)):
      assert target_class is None, (
          'Multiple plugins class found in %s' % plugin_name)
      target_class = obj
  return target_class


def GetPluginNameFromClass(plugin_class):
  """Returns the 'name' of the given plugin class.

  The name is defined as the plugin module path *after*
  `cros.factory.goofy.plugins` and *without* the class name.

  For example, for a plugin class StatusMonitor that is implemented under
  //py/goofy/plugins/status_monitor/status_monitor.py, the name would be
  'status_monitor.status_monitor'.

  For a plugin class TimeSanitizer that is implemented under
  //py/goofy/plugins/time_saniitzer.py, the name would be 'time_sanitizer'.
  """
  if (not issubclass(plugin_class, Plugin) or
      not plugin_class.__module__.startswith(_PLUGIN_MODULE_BASE)):
    raise RuntimeError('%r is not a valid Goofy plugin' % plugin_class)
  return plugin_class.__module__[len(_PLUGIN_MODULE_BASE) + 1:]


class MenuItem:
  """Menu item used by Plugin.

  Properties:
    id: A unique ID used for identify each plugin menu item.
    text: The text to be shown in the menu list.
    callback: The callback function called when the item is click. The callback
      function should always return `ReturnData`.
    eng_mode_only: Only show the item in engineering mode.
  """

  Action = type_utils.Enum(['SHOW_IN_DIALOG', 'RUN_AS_JS'])
  """Action to be executed in Goofy frontend after callback finished."""

  ReturnData = collections.namedtuple('ReturnData', ['action', 'data'])
  """Data to be returned after the execution of menu item callback.

  `action` should be one of the action defined in `Action`, and the `data` would
  be used by the frontend according to `action`.
  """

  def __init__(self, text, callback, eng_mode_only=False):
    self.id = str(uuid.uuid4())
    self.text = text
    self.callback = callback
    self.eng_mode_only = eng_mode_only


def RPCFunction(func):
  """Decorator used in `Plugin` to expose a function to Goofy server."""
  func.__rpc_function__ = True
  return func


class Plugin:
  """Based class for Goofy plugin.

  Plugins are separated components that can be loaded by goofy for different
  scenarios. The subclass can implement the following lifetime functions for
  different purposes.

  `OnStart`: Called when Goofy starts to run the plugin.
  `OnStop`: Called when Goofy is requested to stop or pause the plugin.
  `OnDestroy`: Called when Goofy is going to shutdown.
  """

  STATE = type_utils.Enum(['RUNNING', 'STOPPED', 'DESTROYED'])
  """State of the plugin.

  Goofy plugins are started by Goofy during initialization, and are stopped when
  Goofy is about to shutdown. During the tests, some plugins may also be paused
  temporarily.

  Therefore, a plugin can be in one of the three states:
  - RUNNING: `OnStart` is called and the plugin is running.
  - STOPPED: `OnStop` is called and the plugin is stopped / paused.
  - DESTORYED: `OnDestory` is called and Goofy is going to shutdown.
  """

  class RPCInstance:
    pass

  def __init__(self, goofy, used_resources=None):
    """Constructor

    Args:
      goofy: the goofy instance.
      used_resources: A list of resources accessed by this plugin. Should be
          applied by subclass.
    """
    self.goofy = goofy
    self.used_resources = used_resources or []
    self._state = self.STATE.STOPPED
    self._rpc_instance = None

  def OnStart(self):
    """Called when Goofy starts or resumes the plugin."""

  def OnStop(self):
    """Called when Goofy stops or pauses the plugin."""

  def OnDestroy(self):
    """Called when Goofy is going to be shutdown."""

  def GetRPCInstance(self):
    """Returns RPC instance of the plugin."""

    if self._rpc_instance is None:
      self._rpc_instance = self.RPCInstance()
      for name, attr in inspect.getmembers(self):
        if getattr(attr, '__rpc_function__', False):
          self._rpc_instance.__dict__[name] = attr

    return self._rpc_instance

  def GetMenuItems(self):
    """Returns menu items supported by this plugin."""
    return []

  def GetUILocation(self):
    """Returns where the plugin UI components should be at.

    The return value should be one of [False, True, 'testlist', 'console',
    'goofy-full'], where False means there's no UI, True is same as 'testlist',
    and 'testlist', 'console', 'goofy-full' indicates the location of the UI on
    Goofy.

    The default implementation returns False. Subclass should implement this
    if it has frontend UI. The static files should be in a folder name 'static'
    under the same folder of the python implementation. And the entry point
    would be a HTML file with the same name of the plugin folder.

    For example, a plugin call StatusMonitor can have following setup:

    //py/goofy/plugins/status_monitor/status_monitor.py
    //py/goofy/plugins/status_monitor/static/status_monitor.html
    //py/goofy/plugins/status_monitor/static/status_monitor.js
    //py/goofy/plugins/status_monitor/static/status_monitor.css
    """
    return False

  @debug_utils.CatchException('Plugin')
  def Start(self):
    """Starts running the plugin."""
    if self._state == self.STATE.STOPPED:
      self._state = self.STATE.RUNNING
      self.OnStart()

  @debug_utils.CatchException('Plugin')
  def Stop(self):
    """Stops running the plugin."""
    if self._state == self.STATE.RUNNING:
      self._state = self.STATE.STOPPED
      self.OnStop()

  @debug_utils.CatchException('Plugin')
  def Destroy(self):
    """Destroy the plugin."""
    if self._state == self.STATE.DESTROYED:
      return
    self.Stop()
    self._state = self.STATE.DESTROYED
    self.OnDestroy()
