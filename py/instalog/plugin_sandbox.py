# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog plugin sandbox.

Loads the plugin class instance (using plugin_loader), manages the plugin's
state, and implements PluginAPI functions for the plugin.
"""

import inspect
import logging
import os
import threading
import time

from cros.factory.instalog import datatypes
from cros.factory.instalog import flow_policy
from cros.factory.instalog import json_utils
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog import plugin_loader
from cros.factory.instalog.utils import debug_utils
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import sync_utils
from cros.factory.instalog.utils import time_utils
from cros.factory.instalog.utils import type_utils


# The maximum number of unexpected accesses to store for debugging purposes.
# This is for both unittests and debugging purposes (assuming that the
# PluginSandbox instance can be accessed during runtime).
_UNEXPECTED_ACCESSES_MAX = 5

# Possible plugin states.
STARTING = 'STARTING'
UP = 'UP'
STOPPING = 'STOPPING'
FLUSHING = 'FLUSHING'
DOWN = 'DOWN'
PAUSING = 'PAUSING'
PAUSED = 'PAUSED'
UNPAUSING = 'UNPAUSING'


# TODO(kitching): Find a better home for this class definition.
class CoreAPI:
  """Defines the API a sandbox should use interact with Instalog core."""

  def Emit(self, plugin, events):
    """See Core.Emit."""
    raise NotImplementedError

  def NewStream(self, plugin):
    """See Core.NewStream."""
    raise NotImplementedError

  def GetProgress(self, plugin):
    """See Core.GetProgress."""
    raise NotImplementedError

  def GetNodeID(self):
    """See Core.GetNodeID."""
    raise NotImplementedError


class PluginSandbox(plugin_base.PluginAPI, log_utils.LoggerMixin):
  """Represents a running instance of a particular plugin.

  Implementation for non-PluginAPI functions is not thread-safe.  I.e., you
  should not give multiple threads access to a PluginSandbox object, and run
  Stop() and Pause() simultaneously.  Bad things will happen.  Plugins, however,
  are expected to be able to run multiple threads, and run multiple PluginAPI
  functions simultaneously.  This is expected behaviour.
  """

  # Different actions to take when a call is made into PluginAPI functions.  See
  # the _AskGatekeeper function.
  _ALLOW = 'allow'
  _WAIT = 'wait'
  _ERROR = 'error'

  # Commonly-used sets of Gatekeeper permissions.
  _GATEKEEPER_ALLOW_ALL = {
      STARTING: _ALLOW,
      UP: _ALLOW,
      STOPPING: _ALLOW,
      FLUSHING: _ALLOW,
      DOWN: _ERROR,
      PAUSING: _ALLOW,
      PAUSED: _ALLOW,
      UNPAUSING: _ALLOW}
  _GATEKEEPER_ALLOW_UP = {
      STARTING: _WAIT,
      UP: _ALLOW,
      STOPPING: _WAIT,
      FLUSHING: _ALLOW,
      DOWN: _ERROR,
      PAUSING: _WAIT,
      PAUSED: _WAIT,
      UNPAUSING: _WAIT}
  _GATEKEEPER_ALLOW_UP_PAUSING_STOPPING = {
      STARTING: _WAIT,
      UP: _ALLOW,
      STOPPING: _ALLOW,
      FLUSHING: _ALLOW,
      DOWN: _ERROR,
      PAUSING: _ALLOW,
      PAUSED: _WAIT,
      UNPAUSING: _WAIT}

  def __init__(self, plugin_type, plugin_id=None, superclass=None, config=None,
               policy=None, store_path=None, data_dir=None, core_api=None,
               _plugin_class=None):
    """Initializes the PluginSandbox.

    Args:
      plugin_type: The plugin type of this entry.  Corresponds to the filename
                   of the plugin.
      plugin_id: The unique identifier of this plugin entry.  One plugin type
                 may have multiple plugin entries with different IDs.  If
                 unspecified, will default to the same as plugin_type.
      superclass: The superclass of this plugin.  Can be one of:
                  BufferPlugin, InputPlugin, OutputPlugin.  If unspecified,
                  will allow any of the three types to be created.
      config: Configuration dict of the plugin entry.  Defaults to an empty
              dict.
      policy: FlowPolicy object describing the allow/deny policy of this
              plugin.
      store_path: Path to this plugin's data store file.
      data_dir: Path to the the data directory of this plugin.
      core_api: Reference to an object that implements CoreAPI, usually Core.
                Defaults to an instance of the CoreAPI interface, which will
                throw NotImplementedError when any method is called.  This may
                be acceptible for testing.
      _plugin_class: A "pre-loaded" plugin class for the plugin in question.
                     If provided, the module "loading" and "unloading" steps are
                     skipped, and the plugin class is directly initialized.  For
                     testing purposes.
    """
    self.plugin_type = plugin_type
    self.plugin_id = plugin_id or plugin_type
    self.config = config or {}
    # Allow all events by default (usually used by run_plugin or testing).
    self._policy = policy or flow_policy.FlowPolicy(allow=[{'rule': 'all'}])
    self._store_path = store_path
    if self._store_path:
      self.store = self._LoadStore(self._store_path)
    else:
      self.store = {}
    self._data_dir = data_dir
    self._core_api = core_api or CoreAPI()
    if not isinstance(self._core_api, CoreAPI):
      raise TypeError('Invalid CoreAPI object provided')

    # Create a logger this class to use.
    self.logger = logging.getLogger('%s.plugin_sandbox' % self.plugin_id)

    self._loader = plugin_loader.PluginLoader(
        self.plugin_type, plugin_id=self.plugin_id,
        superclass=superclass, config=self.config, store=self.store,
        plugin_api=self, _plugin_class=_plugin_class)
    self._plugin = None
    self._state = DOWN
    self._event_stream_map = {}

    # Store the target processed event count and timeout for FLUSHING state.
    self._flushing_target = None
    self._flushing_timeout = None

    # Store information about the last _UNEXPECTED_ACCESSES_MAX unexpected
    # accesses.
    self._unexpected_accesses = []

    # Store the last exception caused by SetUp, Main or TearDown.
    self._last_exception = None

    self._setup_thread = None
    self._main_thread = None
    self._teardown_thread = None

  def __repr__(self):
    """Implements repr function for debugging."""
    return ('PluginSandbox(%s, state=%s)'
            % (self.plugin_id, self._state))

  def _LoadStore(self, store_path):
    """Loads the data store dictionary from disk.

    Only used when the plugin is first initialized.
    """
    if not os.path.isfile(store_path):
      return {}
    with open(store_path) as f:
      return json_utils.JSONDecoder().decode(f.read())

  def GetSuperclass(self):
    """Get the superclass of the plugin class.

    Returns:
      None if _plugin_class is not specified and GetClass() has not yet been
      run.  Afterwards, one of BufferPlugin, InputPlugin, or OutputPlugin.
    """
    return self._loader.GetSuperclass()

  def CallPlugin(self, method_name, *args, **kwargs):
    """Safely calls a method of the plugin instance.

    Args:
      method_name: Name of the method being called (string).
      allowed_exceptions: A list of exceptions that the plugin is expected to
                          raise.  These exceptions will be directly raised back
                          to the caller unmodified.

    Returns:
      The value returned by the called plugin method.

    Raises:
      PluginCallError if the plugin raises any unexpected exceptions.
      Any exception in allowed_exceptions may also be raised.
    """
    # TODO(kitching): Test this in unittest.
    # TODO(kitching): Figure out what to do in the case when a
    #                 BufferEventStream is returned.
    allowed_exceptions = tuple(kwargs.pop('allowed_exceptions', ()))
    try:
      ret = getattr(self._plugin, method_name)(*args, **kwargs)
    except allowed_exceptions:  # pylint: disable=catching-non-exception,try-except-raise
      raise
    except Exception as e:
      raise plugin_base.PluginCallError(
          'Plugin call for %s unexpectedly failed.' % self.plugin_id) from e
    return ret


  def _RecordUnexpectedAccess(self, plugin_ref, caller_name, stack):
    """Record an unexpected access from the plugin (i.e. in a stopped state).

    At most _UNEXPECTED_ACCESSES_MAX entries are stored in
    self._unexpected_accesses for debugging purposes.  This function is not
    thread-safe, so it is possible that unexpected accesses may be inserted
    out-of-order, or more than _UNEXPECTED_ACCESSES_MAX entries will be removed
    in the while loop.
    """
    self._unexpected_accesses.insert(0, {
        'caller_name': caller_name,
        'plugin_id': self.plugin_id,
        'plugin_ref': plugin_ref,
        'plugin_type': self.plugin_type,
        'stack': stack,
        'state': self._state,
        'timestamp': time.time()})
    while len(self._unexpected_accesses) > _UNEXPECTED_ACCESSES_MAX:
      self._unexpected_accesses.pop()

  def _AskGatekeeper(self, plugin, state_map):
    """Ensure a plugin is properly registered and in the correct state.

    Args:
      plugin: The plugin that has made the call to core.
      state_map: A map of states to their actions.  Actions can be one of:
                 self._ALLOW, self._WAIT, self._ERROR.

    Raises:
      WaitException if the plugin is currently unable to perform the
      requested operation (action is self._WAIT).

      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not
      (action is self._ERROR).
    """
    caller_name = debug_utils.GetCallerName()
    self.debug('_AskGatekeeper for plugin %s (%s) on function %s',
               self.plugin_id, self._state, caller_name)

    # Ensure that the plugin instance is currently registered.  If the plugin
    # has previously been restarted, and some remaining threads are still
    # attempting to access core, we need to record the access for debugging
    # purposes.
    if plugin is not self._plugin:
      self._RecordUnexpectedAccess(plugin, caller_name, inspect.stack())
      self.critical(
          'Plugin %s (%s) called core %s: Unexpected plugin instance',
          self.plugin_id, self._state, caller_name)
      raise plugin_base.UnexpectedAccess

    # Map the plugin's state to our action (default self._ERROR).
    action = state_map.get(self._state, self._ERROR)

    if action is self._WAIT:
      self.info(
          'Plugin %s (%s) called core %s: Currently in a paused state',
          self.plugin_id, self._state, caller_name)
      raise plugin_base.WaitException

    if action is self._ERROR:
      self._RecordUnexpectedAccess(plugin, caller_name, inspect.stack())
      self.info(
          'Plugin %s (%s) called core %s: Unexpected access',
          self.plugin_id, self._state, caller_name)
      raise plugin_base.UnexpectedAccess

  def _CheckStateCommand(self, allowed_states):
    """Checks to see whether a state command may be run.

    Args:
      allowed_states: A list of allowed states for this state command.

    Raises:
      StateCommandError if not allowed to use the given transition state
      command.
    """
    if not isinstance(allowed_states, list):
      allowed_states = [allowed_states]
    caller_name = debug_utils.GetCallerName()
    self.debug(
        '_CheckStateCommand for plugin %s (%s) on function %s',
        self.plugin_id, self._state, caller_name)
    if self._state not in allowed_states:
      raise plugin_base.StateCommandError(
          'Plugin %s (%s) called %s, but only allowed for %s'
          % (self.plugin_id, self._state, caller_name, allowed_states))

  def GetState(self):
    """Returns the current state of the plugin."""
    self.debug('GetState called: %s', self._state)
    return self._state

  def GetProgress(self):
    """Returns the current progress through buffer for the specified plugin.

    Args:
      plugin: PluginSandbox object requesting BufferEventStream.

    Returns:
      A tuple (completed_count, total_count) representing how many Events have
      been processed so far, and how many exist in total.
    """
    return self._core_api.GetProgress(self)

  def IsLoaded(self):
    """Returns whether the plugin is currently loaded (not DOWN)."""
    self.debug('IsLoaded called: %s', self._state)
    return self._state is not DOWN

  def _Load(self):
    """Asks the PluginLoader factory to give us a new plugin instance."""
    assert self._plugin is None
    self._plugin = self._loader.Create()

  def Start(self, sync=False):
    """Starts the plugin."""
    self._CheckStateCommand(DOWN)
    self._Load()
    self._state = STARTING
    if sync:
      self.AdvanceState(sync)

  def Stop(self, sync=False):
    """Stops the plugin."""
    self._CheckStateCommand([UP, PAUSED])
    self._state = STOPPING
    if sync:
      self.AdvanceState(sync)

  def Flush(self, timeout, sync=False):
    """Flushes the plugin.

    Returns:
      If the sync argument is True, Flush will run asynchronously.  True or
      False will be returned depending on whether the sync succeeded within the
      specified timeout.
    """
    self._CheckStateCommand([UP, PAUSED])

    # Prepare flushing_timeout and flushing_target for AdvanceState.
    self._flushing_timeout = time_utils.MonotonicTime() + timeout
    unused_completed_count, flushing_target = self.GetProgress()
    self._flushing_target = flushing_target
    self._state = FLUSHING

    if sync:
      self.AdvanceState(sync)

      # Check to see if the flushing target has been surpassed.
      current_count, unused_total_count = self.GetProgress()
      return current_count >= flushing_target

    return None

  def Pause(self, sync=False):
    """Pauses the plugin."""
    self._CheckStateCommand(UP)
    self._state = PAUSING
    if sync:
      self.AdvanceState(sync)

  def Unpause(self, sync=False):
    """Unpauses the plugin."""
    self._CheckStateCommand(PAUSED)
    self._state = UNPAUSING
    if sync:
      self.AdvanceState(sync)

  def TogglePause(self, sync=False):
    """Toggles the paused state on the plugin."""
    self._CheckStateCommand([UP, PAUSED])
    if self._state is UP:
      self.Pause(sync)
    elif self._state is PAUSED:
      self.Unpause(sync)

  def AdvanceState(self, sync=False):
    """Runs state machine transitions.

    Needs an external thread to periodically run AdvanceState to run any pending
    actions to take the plugin into its next requested state.  For example, if
    the state has been set to STOPPING, AdvanceState takes care of running the
    appropriate actions and taking the plugin into the STOPPED state.

    Args:
      sync: Whether or not the call should be synchronous.  E.g. if the state
            has been set to STOPPING, AdvanceState won't return until the plugin
            has been stopped.
    """
    # TODO(kitching): Test SpawnFn and exception handling in unittest.
    def SpawnFn(fn, sync=False):
      """Spawns a function in a thread and captures any exceptions thrown.

      If we just let an exception go by uncaptured, it would be displayed to
      stdout, but would go uncaptured by logging (which means only running
      Instalog in the foreground would show the exception).  Additionally, we
      wouldn't have any way of when knowing the plugin encountered some failure.

      Instead, we wrap calls to the plugin and capture exceptions, logging them
      without re-raising.  The last exception is saved into self._last_exception
      for further processing in the next call to AdvanceState.
      """
      def RunAndCaptureException(fn):
        try:
          fn()
        except Exception as e:
          self._last_exception = e
          self.exception('Exception caused by %s', fn.__name__)
      t = threading.Thread(target=RunAndCaptureException, args=(fn,))
      t.start()
      if sync:
        t.join()
      return t

    # Check for the existence of self._last_exception, which denotes that the
    # plugin thread spawned by SpawnFn encountered an error.  Deal with the
    # error appropriately.
    if self._last_exception:
      self.debug('AdvanceState last_exception exists')
      self._last_exception = None
      if self._state is DOWN:
        self.error('Exception occurred, current state is DOWN')
      else:
        self.error('Exception occurred, forcing state to STOPPING')
        self._state = STOPPING

    # If we are in a stage where the main thread should be running, but it has
    # stopped, something must have gone wrong.  Force the plugin into a
    # STOPPING state.
    # TODO(kitching): Come up with a better way of differentiating plugins which
    #                 define Main, and those which do not.
    if (self._state in (UP, PAUSING, PAUSED) and
        'Main' in self._plugin.__class__.__dict__ and
        not self._main_thread.is_alive()):
      self.debug('AdvanceState unexpected main thread dead')
      self.error('Main thread died unexpectedly, '
                 'forcing state to STOPPING')
      self._state = STOPPING

    if self._state is STARTING:
      self.debug('AdvanceState on STARTING')
      if not self._setup_thread:
        self._setup_thread = SpawnFn(self._plugin.SetUp, sync)
      if self._setup_thread and not self._setup_thread.is_alive():
        self._setup_thread = None
        self._main_thread = SpawnFn(self._plugin.Main)
        self._state = UP

    elif self._state is STOPPING:
      self.debug('AdvanceState on STOPPING')
      if self._main_thread and sync:
        self._main_thread.join()
      if self._main_thread and not self._main_thread.is_alive():
        self._main_thread = None
        self._teardown_thread = SpawnFn(self._plugin.TearDown, sync)
      if self._teardown_thread and not self._teardown_thread.is_alive():
        self._teardown_thread = None
        self._plugin = None
        self._state = DOWN

    elif self._state is FLUSHING:
      self.debug('AdvanceState on FLUSHING')
      if not self._flushing_target or not self._flushing_timeout:
        self._flushing_target = None
        self._flushing_timeout = None
        self._state = UP

      flushing_target = self._flushing_target
      flushing_timeout = self._flushing_timeout

      def FlushingTargetReached():
        current_count, unused_completed_count = self.GetProgress()
        return current_count >= flushing_target

      if sync:
        try:
          sync_utils.WaitFor(
              condition=FlushingTargetReached,
              timeout_secs=flushing_timeout - time_utils.MonotonicTime() + 0.5,
              poll_interval=0.5)
        except type_utils.TimeoutError:
          pass

      if (FlushingTargetReached() or
          time_utils.MonotonicTime() >= flushing_timeout):
        self._flushing_target = None
        self._flushing_timeout = None
        self._state = UP

    elif self._state is PAUSING:
      self.debug('AdvanceState on PAUSING')
      if not self._event_stream_map:
        self._state = PAUSED

    elif self._state is UNPAUSING:
      self.debug('AdvanceState on UNPAUSING')
      self._state = UP

  ############################################################
  # Functions below implement plugin_base.PluginAPI.
  ############################################################

  def SaveStore(self, plugin):
    """See PluginAPI.SaveStore."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_ALL)
    self.debug('SaveStore called with state=%s', self._state)
    with file_utils.AtomicWrite(self._store_path) as f:
      f.write(json_utils.JSONEncoder().encode(self.store))

  def GetDataDir(self, plugin):
    """See PluginAPI.GetDataDir."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_ALL)
    self.debug('GetDataDir called with state=%s', self._state)
    return self._data_dir

  def GetNodeID(self, plugin):
    """See PluginAPI.GetNodeID."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_ALL)
    self.debug('GetNodeID called with state=%s', self._state)
    return self._core_api.GetNodeID()

  def IsStopping(self, plugin):
    """See PluginAPI.IsStopping."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_ALL)
    self.debug('IsStopping called with state=%s', self._state)
    return self._state is STOPPING

  def IsFlushing(self, plugin):
    """See PluginAPI.IsFlushing."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_ALL)
    self.debug('IsFlushing called with state=%s', self._state)
    if self._state is not FLUSHING:
      return False
    # Flushing may have already completed, despite the state not having left
    # FLUSHING yet.  Check on the flushing target manually.
    flushing_target = self._flushing_target
    if flushing_target:
      completed_count, unused_total_count = self.GetProgress()
      if completed_count >= flushing_target:
        return False
    return True

  def Emit(self, plugin, events):
    """See PluginAPI.Emit."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_UP)
    self.debug('Emit called with state=%s', self._state)

    # TODO(kitching): Relocate the ProcessStage annotation into Core.
    process_stage = datatypes.ProcessStage(
        node_id=self._core_api.GetNodeID(),
        time=time.time(),
        plugin_id=self.plugin_id,
        plugin_type=self.plugin_type,
        target=datatypes.ProcessStage.BUFFER)
    for event in events:
      # Add the current step in this event's processing history.
      event.AppendStage(process_stage)
    return self._core_api.Emit(self, events)

  def NewStream(self, plugin):
    """See PluginAPI.NewStream."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_UP_PAUSING_STOPPING)
    self.debug('NewStream called with state=%s', self._state)

    buffer_stream = self._core_api.NewStream(self)
    plugin_stream = datatypes.EventStream(plugin, self)
    self._event_stream_map[plugin_stream] = buffer_stream
    return plugin_stream

  def EventStreamNext(self, plugin, plugin_stream, timeout=1):
    """See PluginAPI.EventStreamNext."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_UP)
    self.debug('EventStreamNext called with state=%s', self._state)
    if plugin_stream not in self._event_stream_map:
      raise plugin_base.UnexpectedAccess
    ret = self._NextMatchingEvent(plugin_stream, timeout)
    if ret:
      # TODO(kitching): Relocate the ProcessStage annotation into Core.
      process_stage = datatypes.ProcessStage(
          node_id=self._core_api.GetNodeID(),
          time=time.time(),
          plugin_id=self.plugin_id,
          plugin_type=self.plugin_type,
          target=datatypes.ProcessStage.EXTERNAL)
      ret.AppendStage(process_stage)
    return ret

  def _NextMatchingEvent(self, plugin_stream, timeout):
    """Retrieves the next event matching the plugin's FlowPolicy.

    Args:
      plugin_stream: A stream of events for an output plugin to process.
      timeout: Seconds to wait for retrieving next event.

    Returns:
      None if timeout or no events are available.
    """
    try:
      def CheckEvent(event):
        return event is None or self._policy.MatchEvent(event)

      return sync_utils.PollForCondition(
          poll_method=self._event_stream_map[plugin_stream].Next,
          condition_method=CheckEvent,
          timeout_secs=timeout,
          poll_interval_secs=0)
    except type_utils.TimeoutError:
      return None

  def EventStreamCommit(self, plugin, plugin_stream):
    """See PluginAPI.EventStreamCommit."""
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_UP_PAUSING_STOPPING)
    self.debug('EventStreamCommit called with state=%s', self._state)
    self._RecordUnexpectedAccess(plugin, 'EventStreamAbort', inspect.stack())
    if plugin_stream not in self._event_stream_map:
      raise plugin_base.UnexpectedAccess
    return self._event_stream_map.pop(plugin_stream).Commit()

  def EventStreamAbort(self, plugin, plugin_stream):
    """See PluginAPI.EventStreamAbort."""
    # TODO(kitching): Test in unittest.
    self._AskGatekeeper(plugin, self._GATEKEEPER_ALLOW_UP_PAUSING_STOPPING)
    self.debug('EventStreamAbort called with state=%s', self._state)
    self._RecordUnexpectedAccess(plugin, 'EventStreamAbort', inspect.stack())
    if plugin_stream not in self._event_stream_map:
      raise plugin_base.UnexpectedAccess
    # If no events were processed, use Commit() instead of Abort().  This
    # accounts for the case where all events were skipped because of the
    # FlowPolicy.  If no "valid" events are ever encountered, the plugin's
    # consumer will never advance through the buffer, which could cause it to
    # grow without the possibility of truncation.  Thus we force Commit() to
    # make sure any events "hidden" by the FlowPolicy are committed.
    if plugin_stream.GetCount() == 0:
      return self._event_stream_map.pop(plugin_stream).Commit()
    return self._event_stream_map.pop(plugin_stream).Abort()
