# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog plugin loader.

If this module is imported directly as `plugin_loader` instead of its full
`instalog.plugin_loader`, and the plugin it is loading also includes
`instalog.plugin_loader`, it will cause duplicate copies of this module to be
loaded.  Beware.
"""

from __future__ import print_function

import inspect
import logging
import sys

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils import arg_utils


_DEFAULT_PLUGIN_PREFIX = 'instalog.plugins.'


class PluginLoader(object):
  """Factory to create instances of a particular plugin configuration."""

  def __init__(self, plugin_type, plugin_id=None, superclass=None, config=None,
               core_api=None, _plugin_prefix=_DEFAULT_PLUGIN_PREFIX,
               _module_ref=None):
    """Initializes the PluginEntry.

    Args:
      plugin_type: See plugin_instance.PluginInstance.
      plugin_id: See plugin_instance.PluginInstance.
      superclass: See plugin_instance.PluginInstance.
      config: See plugin_instance.PluginInstance.
      core_api: Reference to an object that implements plugin_base.CoreAPI.
                Defaults to an instance of the CoreAPI interface, which will
                throw NotImplementedError when any method is called.  This may
                be acceptible for testing.
      _plugin_prefix: The prefix where the plugin module should be found.
                      Should include the final ".".  Defaults to
                      _DEFAULT_PLUGIN_PREFIX.
      _module_ref: A "pre-imported" module object for the plugin in question.
                   If provided, the "loading" and "unloading" steps are skipped.
    """
    self.plugin_type = plugin_type
    self.plugin_id = plugin_id or plugin_type
    self.superclass = superclass or plugin_base.Plugin
    self.config = config or {}
    self._core_api = core_api or plugin_base.CoreAPI()
    self._plugin_prefix = _plugin_prefix
    self._module_ref = _module_ref
    self._possible_module_names = None

    # Check that the provided core_api is valid.
    if not isinstance(self._core_api, plugin_base.CoreAPI):
      self._ReportException('Provided core_api object is invalid')

    # Create a logger for the plugin to use.
    self._logger = logging.getLogger('%s.plugin' % self.plugin_id)

  def _ReportException(self, message=None):
    """Reports a LoadPluginError exception with specified message.

    Uses the current stack's last exception traceback if it exists.

    Args:
      message: Message to use.  Default is to use the message from the current
               stack's last exception.
    """
    _, exc, tb = sys.exc_info()
    exc_message = message or '%s: %s' % (exc.__class__.__name__, str(exc))
    new_exc = plugin_base.LoadPluginError(
        'Plugin %s encountered an error loading: %s'
        % (self.plugin_id, exc_message))
    raise new_exc.__class__, new_exc, tb

  def _GetPossibleModuleNames(self):
    if not self._possible_module_names:
      self._possible_module_names = [
          '%s%s.%s' % (self._plugin_prefix, self.plugin_type, self.plugin_type),
          '%s%s' % (self._plugin_prefix, self.plugin_type)]
    return self._possible_module_names

  def _LoadModule(self):
    """Locates the plugin's Python module and returns a reference.

    Returns:
      The plugin's Python module object.

    Raises:
      LoadPluginError if the plugin could not be found, or if some other problem
      was encountered while loading (for example, a syntax error).
    """
    if self._module_ref:
      return self._module_ref
    for search_name in self._GetPossibleModuleNames():
      # Get a reference to the module.  This will raise ImportError if it
      # doesn't exist.
      try:
        __import__(search_name)
        return sys.modules[search_name]
      except ImportError as e:
        if e.message.startswith('No module named'):
          continue
        # Any other ImportError problem.
        self._ReportException()
      except Exception as e:
        # Any other exception -- probably SyntaxError.
        self._ReportException()
    # Uses traceback from the last ImportError.
    self._ReportException('No module named %s'
                          % ' or '.join(self._GetPossibleModuleNames()))

  def _UnloadModule(self):
    """Unloads the module from Python.

    If we have already loaded the module previously, unload it first.
    This ensures we catch the case where the file no longer exists when
    we re-import the module.
    """
    if self._module_ref:
      return
    for search_name in self._GetPossibleModuleNames():
      try:
        del sys.modules[search_name]
      except KeyError:
        pass

  def GetClass(self):
    # Unload any references to the module before and after loading.
    self._UnloadModule()
    module_ref = self._LoadModule()
    self._UnloadModule()

    # Search for the correct class object within the module.
    def IsSubclass(cls):
      return (inspect.isclass(cls) and
              issubclass(cls, self.superclass) and
              cls.__module__ in self._GetPossibleModuleNames())
    plugin_classes = inspect.getmembers(module_ref, IsSubclass)
    if len(plugin_classes) != 1:
      self._ReportException(
          '%s contains %d plugin classes; only 1 is allowed per file'
          % (self.plugin_type, len(plugin_classes)))
    # getmembers returns a list of tuples: (binding_name, value).
    return plugin_classes[0][1]

  def Create(self):
    """Create an instance of the particular plugin class.

    Args:
      core: A handle to the core object.  Injected into the plugin instance.

    Raises:
      LoadPluginError if the plugin file does not exist.
    """
    # Instantiate the plugin with the requested configuration.
    plugin_class = self.GetClass()
    try:
      return plugin_class(self.config, self._logger, self._core_api)
    except arg_utils.ArgError as e:
      self._ReportException('Error parsing arguments: %s' % e.message)
    except Exception:
      self._ReportException()
