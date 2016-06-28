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


class PluginCallError(Exception):
  """An error occurred when calling a method on the plugin instance."""
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
    """Returns whether or not the plugin may continue running.

    If True is returned, the plugin should continue running as usual.  If False
    is returned, the plugin should shut down as soon as it finishes its work.
    Should be checked regularly in the Main thread, as well as any other threads
    started by the plugin.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.IsStopping(self)


class BufferPlugin(Plugin):
  """Base class for a buffer plugin in Instalog."""

  def AddConsumer(self, consumer_id):
    """Subscribes the specified consumer ID to the buffer.

    Args:
      consumer_id: Unique identifier of the consumer being added.
    """
    raise NotImplementedError

  def RemoveConsumer(self, consumer_id):
    """Unsubscribes the specified consumer ID from the buffer.

    Args:
      consumer_id: Unique identifier of the consumer being removed.
    """
    raise NotImplementedError

  def ListConsumers(self):
    """Returns a list of consumers currently subscribed to the buffer."""
    # TODO(kitching): Should we return the status of each consumer in this
    #                 function, or should it be separated into ConsumerStatus()?
    raise NotImplementedError

  def Produce(self, events):
    """Produces events to be stored into the buffer.

    Args:
      events: List of Event objects to be inserted into the buffer.

    Returns:
      True if successful, False otherwise.
    """
    raise NotImplementedError

  def Consume(self, consumer_id):
    """Returns a BufferEventStream to consume events from the buffer.

    Args:
      consumer_id: ID of the consumer for which to create a BufferEventStream.

    Returns:
      True if successful, False otherwise.
    """
    raise NotImplementedError


class BufferEventStream(object):
  """Event stream interface that a buffer needs to implement.

  Objects implementing BufferEventStream should be returned when the buffer
  plugin's Consume method is called.
  """

  def Next(self):
    """Returns the next available Event."""
    raise NotImplementedError

  def Commit(self):
    """Marks this batch of Events as successfully processed.

    Marks this BufferEventStream as expired.

    Returns:
      True if successful, False otherwise.  If unsuccessful, this
      BufferEventStream is considered expired, and its Events will be returned
      on subsequent Next calls from other BufferEventStream objects.

    Raises:
      EventStreamExpired if this BufferEventStream is expired.
    """
    raise NotImplementedError

  def Abort(self):
    """Aborts processing this batch of Events.

    Marks this BufferEventStream as expired.  This BufferEventStream's Events
    will still be returned on subsequent Next calls from other BufferEventStream
    objects.

    Raises:
      EventStreamExpired if this BufferEventStream is expired.
    """
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
      An EventStream object (see datatypes module).  None if we currently do not
      have permission to create a new EventStream object (i.e. plugin is not in
      one of the allowed states).

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    try:
      return self._plugin_api.NewStream(self)
    except WaitException:
      return None


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
