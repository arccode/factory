# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog plugin base.

Defines plugin classes (buffer, input, output), and a PluginAPI interface for
plugins to access.
"""

import inspect
import logging
import os
import sys
import time

from cros.factory.instalog import log_utils
from cros.factory.instalog.utils import arg_utils
from cros.factory.instalog.utils import time_utils


class LoadPluginError(Exception):
  """The plugin encountered an error while loading."""


class WaitException(Exception):
  """The plugin currently cannot perform the requested operation."""


class UnexpectedAccess(Exception):
  """The plugin is accessing data when it should be stopped."""


class StateCommandError(Exception):
  """A state command on the plugin sandbox could not be run."""


class EventStreamExpired(Exception):
  """The event stream in question is expired and can no longer be used."""


class PluginCallError(Exception):
  """An error occurred when calling a method on the plugin instance."""


class ConfigError(Exception):
  """An error occurred when loading the config file."""


class PluginAPI:
  """Defines an interface for plugins to call."""

  def SaveStore(self, plugin):
    """See Plugin.SaveStore."""
    raise NotImplementedError

  def GetDataDir(self, plugin):
    """See Plugin.GetDataDir."""
    raise NotImplementedError

  def IsStopping(self, plugin):
    """See Plugin.IsStopping."""
    raise NotImplementedError

  def IsFlushing(self, plugin):
    """See Plugin.IsStopping."""
    raise NotImplementedError

  def Emit(self, plugin, events):
    """See InputPlugin.Emit."""
    raise NotImplementedError

  def NewStream(self, plugin):
    """See OutputPlugin.NewStream."""
    raise NotImplementedError

  def EventStreamNext(self, plugin, plugin_stream, timeout):
    """See BufferEventStream.Next."""
    raise NotImplementedError

  def EventStreamCommit(self, plugin, plugin_stream):
    """See BufferEventStream.Commit."""
    raise NotImplementedError

  def EventStreamAbort(self, plugin, plugin_stream):
    """See BufferEventStream.Abort."""
    raise NotImplementedError


class Plugin(log_utils.LoggerMixin):
  """Base class for a buffer plugin, input plugin, or output plugin in Instalog.

  This is a base class for BufferPlugin, InputPlugin and OutputPlugin.  Plugins
  should subclass from these three classes.

  This base class processes plugin arguments set through the ARGS variable, and
  sets some shortcut functions to the logger.
  """

  def __init__(self, config, logger_name, store, plugin_api):
    """Plugin constructor.

    Args:
      config: A dictionary representing arguments for this plugin.  Will be
              validated against the specification in ARGS.
      logger: A reference to the logger for this plugin instance.
      store: A reference to the plugin's store dictionary.
      plugin_api: An instance of a class implementing PluginAPI.

    Raises:
      arg_utils.ArgError if the arguments fail to validate.
    """
    # Try parsing the arguments according to the spec in ARGS.
    arg_spec = getattr(self, 'ARGS', [])
    self.args = arg_utils.Args(*arg_spec).Parse(config)

    # log_utils.LoggerMixin creates shortcut functions for convenience.
    self.logger = logging.getLogger(logger_name)

    # Plugin data store dictionary.
    self.store = store

    # Save the core API to a private instance variable.
    self._plugin_api = plugin_api

  def SetUp(self):
    """Sets up any connections or threads needed.

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

  def TearDown(self):
    """Shuts down any extra threads and connections used by the plugin.

    This function should only return to the caller after all threads and
    extra processes used by the plugin have stopped.
    """
    return

  def SaveStore(self):
    """Saves the data store dictionary to disk.

    Plugins may make many updates to the store (inefficient to write on every
    change), or might only want to write it to disk in certain situations to
    ensure atomicity.  Thus the action of saving the store is exposed for the
    plugin to handle.
    """
    return self._plugin_api.SaveStore(self)

  def GetDataDir(self):
    """Returns the data directory of this plugin.

    This directory is set aside by Instalog core for the plugin to store any
    data.  Its value can be expected to be consistent across plugin restarts or
    Instalog restarts.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.GetDataDir(self)

  def GetNodeID(self):
    """Returns the node ID of this plugin.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.GetNodeID(self)

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

  def IsFlushing(self):
    """Returns whether or not the plugin is flushing.

    If True is returned, the plugin should continue running as usual.  If False
    is returned, the plugin should process any remaining data, and not wait for
    further data to be included in the current "batch".

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.IsFlushing(self)

  def Sleep(self, secs):
    """Suspends execution of the current thread for the given number of seconds.

    When a plugin is requested to stop, it might be in the middle of a
    time.sleep call.  This provides an alternative sleep function, which will
    return immediately when a plugin changes to the STOPPING state.

    Should typically be used at the end of an iteration of a plugin's Main
    while loop.  For example:

      while not self.IsStopping():
        # ... do some work ...
        self.Sleep(self.args.interval)
    """
    end_time = time_utils.MonotonicTime() + secs
    while (time_utils.MonotonicTime() < end_time and
           (not self.IsStopping() and not self.IsFlushing())):
      time.sleep(min(1, secs))


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

  def ListConsumers(self, details=0):
    """Returns information about consumers subscribed to the buffer.

    Returns:
      A dictionary, where keys are consumer IDs, and values are tuples
      of (completed_count, total_count) representing progress through
      Event processing.
    """
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


class BufferEventStream:
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


class OutputPlugin(InputPlugin):
  """Base class for an output plugin in Instalog.

  An output plugin may also Emit events, thus OutputPlugin inherits from
  InputPlugin as its parent class.
  """

  def NewStream(self):
    """Gets a new EventStream object to retrieve output events.

    Returns:
      An EventStream object (see datatypes module).  None if we currently do not
      have permission to create a new EventStream object (i.e. plugin is not in
      one of the allowed states), or if the data the buffer would need to access
      in the EventStream is currently unavailable.

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
  # pylint: disable=protected-access
  frame_info = inspect.getframeinfo(sys._getframe(1))
  plugin_type = os.path.splitext(os.path.basename(frame_info[0]))[0]
  from cros.factory.instalog import run_plugin
  run_plugin.main(plugin_type)
