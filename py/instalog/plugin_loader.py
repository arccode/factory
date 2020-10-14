# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog plugin loader.

If this module is imported directly as `plugin_loader` instead of its full
`instalog.plugin_loader`, and the plugin it is loading also includes
`instalog.plugin_loader`, it will cause duplicate copies of this module to be
loaded.  Beware.
"""

import imp
import inspect
import logging
import sys

from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils import arg_utils


_DEFAULT_PLUGIN_PREFIX = 'cros.factory.instalog.plugins.'


class PluginLoader:
  """Factory to create instances of a particular plugin configuration."""

  def __init__(self, plugin_type, plugin_id=None, superclass=None, config=None,
               store=None, plugin_api=None,
               _plugin_prefix=_DEFAULT_PLUGIN_PREFIX, _plugin_class=None):
    """Initializes the PluginEntry.

    Args:
      plugin_type: See plugin_sandbox.PluginSandbox.
      plugin_id: See plugin_sandbox.PluginSandbox.
      superclass: See plugin_sandbox.PluginSandbox.
      config: See plugin_sandbox.PluginSandbox.
      plugin_api: Reference to an object that implements plugin_base.PluginAPI.
                   Defaults to an instance of the PluginAPI interface, which
                   will throw NotImplementedError when any method is called.
                   This may be acceptible for testing.
      _plugin_prefix: The prefix where the plugin module should be found.
                      Should include the final ".".  Defaults to
                      _DEFAULT_PLUGIN_PREFIX.  For testing purposes.
      _plugin_class: See plugin_sandbox.PluginSandbox.
    """
    self.plugin_type = plugin_type
    self.plugin_id = plugin_id or plugin_type
    self.config = config or {}
    self._store = store
    if self._store is None:
      self._store = {}
    self._plugin_api = plugin_api or plugin_base.PluginAPI()
    if not isinstance(self._plugin_api, plugin_base.PluginAPI):
      raise TypeError('Invalid PluginAPI object provided')
    self._plugin_prefix = _plugin_prefix
    self._plugin_class = _plugin_class
    self._possible_module_names = None

    # If we have access to the superclass already, store it.
    if superclass:
      self.superclass = superclass
    # Since _plugin_class is for testing, it does not check against
    # given superclass argument.
    elif self._plugin_class:
      self.superclass = self._GetSuperclass(self._plugin_class)
      if not self.superclass:
        raise TypeError('Provided _plugin_class is not a plugin class')
    else:
      self.superclass = plugin_base.Plugin

    # Check that the provided plugin_api is valid.
    if not isinstance(self._plugin_api, plugin_base.PluginAPI):
      self._ReportException('Provided plugin_api object is invalid')

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
    raise new_exc.__class__(new_exc).with_traceback(tb)

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
    for search_name in self._GetPossibleModuleNames():
      # Get a reference to the module.  This will raise ImportError if it
      # doesn't exist.
      #
      # TODO(kitching): This is confusing when there is an error in the
      #                 plugin_name/plugin_name.py, since the error reported
      #                 back is that plugin_name/__init__.py doesn't contain any
      #                 of the proper classes.  Improve this.
      try:
        if search_name in sys.modules:
          # If the module already exists, use reload instead of __import__.
          # Why?  In the case that the file no longer exists on re-import,
          # __import__ would silently ignore and pass a reference to the old
          # module, but reload throws an ImportError.
          return imp.reload(sys.modules[search_name])

        __import__(search_name)
        return sys.modules[search_name]
      except ImportError as e:
        if str(e).startswith('No module named'):
          continue
        # Any other ImportError problem.
        self._ReportException()
      except Exception as e:
        # Any other exception -- probably SyntaxError.
        self._ReportException()
    # Uses traceback from the last ImportError.
    self._ReportException('No module named %s'
                          % ' or '.join(self._GetPossibleModuleNames()))

  def GetClass(self):
    """Returns the Python class object of the plugin.

    Raises:
      LoadPluginError if the plugin could not be found, if some other problem
      was encountered while loading (for example, a syntax error), or if the
      plugin file does not contain a subclass of the requested plugin type.
    """
    # If _plugin_class was provided in __init__, directly return it.
    if self._plugin_class:
      return self._plugin_class

    # Search for the correct class object within the module.
    module_ref = self._LoadModule()
    def IsSubclass(cls):
      return (inspect.isclass(cls) and
              issubclass(cls, self.superclass) and
              # If we are not allowing any type of plugin class
              # (plugin_base.Plugin), then make sure to check that the classes
              # match exactly.  This is needed since OutputPlugin is a subclass
              # of InputPlugin.
              (self.superclass is plugin_base.Plugin or
               self.superclass is self._GetSuperclass(cls)) and
              cls.__module__ in self._GetPossibleModuleNames())
    plugin_classes = inspect.getmembers(module_ref, IsSubclass)
    if len(plugin_classes) != 1:
      self._ReportException(
          '%s contains %d plugin classes; only 1 is allowed per file'
          % (self.plugin_type, len(plugin_classes)))
    # getmembers returns a list of tuples: (binding_name, value).
    cls = plugin_classes[0][1]

    # Store the superclass of the plugin for future reference.
    self.superclass = self._GetSuperclass(cls)

    # Return the plugin class.
    return cls

  @classmethod
  def _GetSuperclass(cls, target_class):
    """Returns the superclass for the given plugin class, or None otherwise."""
    # Since OutputPlugin is a subclass of InputPlugin, OutputPlugin must be
    # checked before InputPlugin.
    for superclass in [plugin_base.BufferPlugin,
                       plugin_base.OutputPlugin,
                       plugin_base.InputPlugin]:
      if issubclass(target_class, superclass):
        return superclass
    return None

  def GetSuperclass(self):
    """Get the superclass of the plugin class.

    Returns:
      None if _plugin_class is not specified and GetClass() has not yet been
      run.  Afterwards, one of BufferPlugin, InputPlugin, or OutputPlugin.
    """
    if self.superclass is plugin_base.Plugin:
      return None
    return self.superclass

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
      return plugin_class(self.config, self._logger.name, self._store,
                          self._plugin_api)
    except arg_utils.ArgError as e:
      self._ReportException('Error parsing arguments: %s' % str(e))
    except Exception:
      self._ReportException()
