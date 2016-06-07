# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog plugin base.

Defines plugin classes (buffer, input, output), and a CoreAPI interface to
interact with Instalog core.
"""

import instalog_common  # pylint: disable=W0611
from instalog.utils import arg_utils


class LoadPluginError(Exception):
  """The plugin encountered an error while loading."""
  pass


class CoreAPI(object):
  """Defines the interface a plugin should use interact with Instalog core."""

  def GetStateDir(self):
    """See Plugin.GetStateDir."""
    raise NotImplementedError

  def IsStopping(self):
    """See Plugin.IsStopping."""
    raise NotImplementedError

  def Emit(self, events):
    """See InputPlugin.Emit."""
    raise NotImplementedError

  def NewStream(self):
    """See OutputPlugin.NewStream."""
    raise NotImplementedError


class Plugin(object):
  """Base class for a buffer plugin, input plugin, or output plugin in Instalog.

  This is a base class for BufferPlugin, InputPlugin and OutputPlugin.  Plugins
  should subclass from these three classes.

  This base class processes plugin arguments set through the ARGS variable, and
  sets some shortcut functions to the logger.
  """

  def __init__(self, config, logger, core_api):
    """Plugin constructor.

    Args:
      config: A dictionary representing arguments for this plugin.  Will be
              validated against the specification in ARGS.
      logger: A reference to the logger for this plugin instance.
      core_api: An instance of a class implementing CoreAPI.

    Raises:
      arg_utils.ArgError if the arguments fail to validate.
    """
    # Try parsing the arguments according to the spec in ARGS.
    arg_spec = getattr(self, 'ARGS', [])
    setattr(self, 'args', arg_utils.Args(*arg_spec).Parse(config))

    # Save the core API to a private instance variable.
    self._core_api = core_api

    # Save the logger and create some shortcut functions for convenience.
    self.logger = logger
    self.debug = logger.debug
    self.info = logger.info
    self.warning = logger.warning
    self.error = logger.error
    self.critical = logger.critical
    self.exception = logger.exception

  def GetStateDir(self):
    """Returns the state directory of this plugin.

    This directory is set aside by Instalog core for the plugin to store any
    state.  Its value can be expected to be consistent across plugin restarts or
    Instalog restarts.
    """
    return self._core_api.GetStateDir()

  def IsStopping(self):
    """Returns whether or not the plugin currently needs to shut down.

    Should be checked regularly in the Main thread, as well as any other threads
    started by the plugin.
    """
    return self._core_api.IsStopping()

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
    """
    return self._core_api.Emit(events)


class OutputPlugin(Plugin):
  """Base class for an output plugin in Instalog."""

  def NewStream(self):
    """Gets a new EventStream object to retrieve output events.

    Returns:
      An EventStream object.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._core_api.NewStream()
