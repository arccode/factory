# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog plugin base.

Defines plugin classes (buffer, input, output), and a PluginAPI interface for
plugins to access.
"""

import inspect
import os

import instalog_common  # pylint: disable=W0611
from instalog.utils import arg_utils


class LoadPluginError(Exception):
  """The plugin encountered an error while loading."""
  pass


class WaitException(Exception):
  """The plugin currently cannot perform the requested operation."""
  pass


class UnexpectedAccess(Exception):
  """The plugin is accessing data when it should be stopped."""
  pass


class StateCommandError(Exception):
  """A state command on the plugin sandbox could not be run."""
  pass


class EventStreamExpired(Exception):
  """The event stream in question is expired and can no longer be used."""
  pass


class PluginAPI(object):
  """Defines an interface for plugins to call."""

  def GetStateDir(self, plugin):
    """See Plugin.GetStateDir."""
    raise NotImplementedError

  def IsStopping(self, plugin):
    """See Plugin.IsStopping."""
    raise NotImplementedError

  def Emit(self, plugin, events):
    """See InputPlugin.Emit."""
    raise NotImplementedError

  def NewStream(self, plugin):
    """See OutputPlugin.NewStream."""
    raise NotImplementedError

  def EventStreamNext(self, plugin, plugin_stream):
    """See PluginSandbox.EventStreamNext."""
    raise NotImplementedError

  def EventStreamCommit(self, plugin, plugin_stream):
    """See PluginSandbox.EventStreamCommit."""
    raise NotImplementedError

  def EventStreamAbort(self, plugin, plugin_stream):
    """See PluginSandbox.EventStreamAbort."""
    raise NotImplementedError


class Plugin(object):
  """Base class for a buffer plugin, input plugin, or output plugin in Instalog.

  This is a base class for BufferPlugin, InputPlugin and OutputPlugin.  Plugins
  should subclass from these three classes.

  This base class processes plugin arguments set through the ARGS variable, and
  sets some shortcut functions to the logger.
  """

  def __init__(self, config, logger, plugin_api):
    """Plugin constructor.

    Args:
      config: A dictionary representing arguments for this plugin.  Will be
              validated against the specification in ARGS.
      logger: A reference to the logger for this plugin instance.
      plugin_api: An instance of a class implementing PluginAPI.

    Raises:
      arg_utils.ArgError if the arguments fail to validate.
    """
    # Try parsing the arguments according to the spec in ARGS.
    arg_spec = getattr(self, 'ARGS', [])
    setattr(self, 'args', arg_utils.Args(*arg_spec).Parse(config))

    # Save the core API to a private instance variable.
    self._plugin_api = plugin_api

    # Save the logger and create some shortcut functions for convenience.
    self.logger = logger
    self.debug = logger.debug
    self.info = logger.info
    self.warning = logger.warning
    self.error = logger.error
    self.critical = logger.critical
    self.exception = logger.exception

  def Start(self):
    """Starts any connections or threads needed.

    This function should return to the caller after the plugin has been
    initialized.
    """
    return

  def Main(self):
    """Main thread of the plugin, started by Instalog.

    Should regularly check self.IsStopping().  In the case that IsStopping()
    returns True, this thread should complete execution as soon as possible.
    """
    return

  def Stop(self):
    """Shuts down any extra threads and connections used by the plugin.

    This function should only return to the caller after all threads and
    extra processes used by the plugin have stopped.
    """
    return

  def GetStateDir(self):
    """Returns the state directory of this plugin.

    This directory is set aside by Instalog core for the plugin to store any
    state.  Its value can be expected to be consistent across plugin restarts or
    Instalog restarts.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.GetStateDir(self)

  def IsStopping(self):
    """Returns whether or not the plugin currently needs to shut down.

    Should be checked regularly in the Main thread, as well as any other threads
    started by the plugin.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.IsStopping(self)


class BufferPlugin(Plugin):
  """Base class for a buffer plugin in Instalog."""

  def AddConsumer(self, cname):
    raise NotImplementedError

  def RemoveConsumer(self, cname):
    raise NotImplementedError

  def ListConsumers(self):
    raise NotImplementedError

  def ConsumerStatus(self, cname):
    raise NotImplementedError

  def Produce(self, events):
    raise NotImplementedError

  def Consume(self, cname):
    raise NotImplementedError


class BufferEventStream(object):

  def Next(self):
    raise NotImplementedError

  def Commit(self):
    raise NotImplementedError

  def Abort(self):
    raise NotImplementedError


class InputPlugin(Plugin):
  """Base class for an input plugin in Instalog."""

  def Emit(self, events):
    """Emits a set of Event objects to be passed to Instalog's buffer.

    Args:
      events: Either a single Event or a list of Event objects to be emitted.

    Returns:
      True on success, False on failure.  In either case, the plugin is
      expected to deal appropriately with retrying, or letting its source know
      that a failure occurred.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    try:
      return self._plugin_api.Emit(self, events)
    except WaitException:
      return False


class OutputPlugin(Plugin):
  """Base class for an output plugin in Instalog."""

  def NewStream(self):
    """Gets a new EventStream object to retrieve output events.

    Returns:
      An EventStream object (see datatypes module).

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.NewStream(self)


def main():
  """Runs plugins as executables.

  Forwards main to plugin_sandbox module.  Plugins can enable their executable
  bit, and include the following __main__ snippet at the bottom in order to
  provide self-running abilities for test purposes:

    if __name__ == '__main__':
      plugin_sandbox.main()

  See plugin_sandbox.main for more details.
  """
  frame_info = inspect.stack()[1]
  plugin_type = os.path.splitext(os.path.basename(frame_info[1]))[0]
  from instalog import run_plugin
  run_plugin.main(plugin_type)
