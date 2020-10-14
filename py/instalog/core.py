# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Fix for bug b/30904731: Import _strptime manually.  Otherwise,
# threads may initially raise the exception `AttributeError: _strptime`.
import logging
import os
import threading
import time
import _strptime  # pylint: disable=unused-import

from cros.factory.instalog import flow_policy
from cros.factory.instalog import json_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog import plugin_sandbox

# pylint: disable=no-name-in-module
from cros.factory.instalog.external.jsonrpclib import SimpleJSONRPCServer


# Possible daemon states.
STARTING = 'STARTING'
UP = 'UP'
STOPPING = 'STOPPING'
DOWN = 'DOWN'


class Instalog(plugin_sandbox.CoreAPI):

  def __init__(self, node_id, data_dir, cli_hostname, cli_port, buffer_plugin,
               input_plugins=None, output_plugins=None):
    """Constructor.

    Args:
      node_id: ID of this Instalog node.
      data_dir: Path to Instalog's state directory.  Plugin state directories
                will be stored here.
      cli_hostname: Hostname used for the CLI RPC server.
      cli_port: Port used for the CLI RPC server.
      buffer_plugin: Configuration dict for the buffer plugin.  Keys should
                     consist of:
                     - plugin: Required, plugin module name.
                     - args: Optional, defines plugin arguments.
      input_plugins: List of configuration dicts for input plugins.
                     Configuration dicts should be the same format as
                     that of buffer_plugin, with the addition of:
                      - targets: Optional, defines target plugins.
      output_plugins: List of configuration dicts for output plugins.
                      - plugin: Required, plugin module name.
                      - args: Optional, defines plugin arguments.
                      - allow: Optional, defines flow policy allow rules.
                      - deny: Optional, defines flow policy deny rules.
                      - targets: Optional, defines target plugins.
    """
    self._rpc_lock = threading.Lock()
    self._state = DOWN

    # Store the node ID.
    self._node_id = node_id

    # Ensure we have a working data directory.
    self._data_dir = data_dir

    # Create plugin sandboxes.
    self._PreprocessConfigEntries(input_plugins, output_plugins)
    self._buffer = self._ConfigEntryToSandbox(
        plugin_base.BufferPlugin, 'buffer', buffer_plugin)
    self._plugins = {}
    self._plugins.update(self._ConfigEntriesToSandboxes(
        plugin_base.InputPlugin, input_plugins))
    self._plugins.update(self._ConfigEntriesToSandboxes(
        plugin_base.OutputPlugin, output_plugins))

    # Start the RPC server.
    self._rpc_server = SimpleJSONRPCServer.SimpleJSONRPCServer(
        (cli_hostname, cli_port))
    self._rpc_server.register_function(self.IsUp)
    self._rpc_server.register_function(self.Stop)
    self._rpc_server.register_function(self.Inspect)
    self._rpc_server.register_function(self.Flush)
    self._rpc_server.register_function(self.GetAllProgress)
    self._rpc_thread = threading.Thread(target=self._rpc_server.serve_forever)
    self._rpc_thread.start()

  def _ShutdownRPCServer(self):
    def ShutdownThread():
      self._rpc_server.shutdown()
      self._rpc_server.server_close()
    t = threading.Thread(target=ShutdownThread)
    t.start()

  def _PreprocessConfigEntries(self, input_plugins, output_plugins):
    """Preprocesses config entries to allow the "targets" argument."""
    # Ensure that plugin IDs don't overlap across input and output.
    if any([plugin_id in output_plugins for plugin_id in input_plugins]):
      raise ValueError

    # Next, convert 'targets' entries to corresponding allow policy rule.
    for dct in [input_plugins, output_plugins]:
      for plugin_id, plugin_config in dct.items():
        if 'targets' in plugin_config:
          targets = plugin_config.pop('targets')
          if not isinstance(targets, list):
            targets = [targets]
          for target in targets:
            if target not in output_plugins:
              raise plugin_base.ConfigError(
                  'Non-existent target output plugin ID `%s\' referenced in '
                  'plugin `%s\' config' % (target, plugin_id))
            target_allow = output_plugins[target].setdefault('allow', [])
            target_allow.append({'rule': 'history',
                                 'plugin_id': plugin_id,
                                 'position': -1})

    # Ensure that all output plugins have at least one event source.
    for plugin_id, plugin_config in output_plugins.items():
      if not plugin_config.get('allow'):
        raise plugin_base.ConfigError(
            'No plugin is targetting output plugin `%s\'.  Please (1) disable '
            'this plugin, (2) add allow/deny rules, or (3) configure '
            '`targets\' of another plugin to point to it.' % plugin_id)


  def _ConfigEntryToSandbox(self, superclass, plugin_id, config):
    """Parses configuration for a particular plugin entry.

    Returns:
      PluginSandbox object representing the plugin.

    Raises:
      ConfigError if the config dict does not include the plugin module to load.
    """
    # The plugin type is included along with its configuration.  Extract it.
    if not isinstance(config, dict) or 'plugin' not in config:
      raise plugin_base.ConfigError(
          'Plugin %s must have a config dictionary which includes the key '
          '`plugin` to specify which plugin module to load' % plugin_id)
    plugin_type = config.pop('plugin')
    allow = config.pop('allow', [])
    deny = config.pop('deny', [])
    args = config.pop('args', {})
    # Disallow recursion by default.  Any events emitted by a plugin should
    # never be processed by that plugin again.
    enable_recursion = config.pop('enable_recursion', False)
    if config:
      raise plugin_base.ConfigError(
          'Plugin %s has extra arguments: %s' % (plugin_id, ', '.join(config)))

    # Create FlowPolicy object.
    policy = flow_policy.FlowPolicy(allow, deny)
    if not enable_recursion:
      policy.deny.append(
          flow_policy.HistoryRule(plugin_id=plugin_id,
                                  node_id=self._node_id))

    # Make sure we have a store_path and data_dir for the plugin.
    store_path = os.path.join(self._data_dir, '%s.json' % plugin_id)
    data_dir = os.path.join(self._data_dir, plugin_id)
    if not os.path.exists(data_dir):
      os.makedirs(data_dir)

    return plugin_sandbox.PluginSandbox(
        plugin_type=plugin_type,
        plugin_id=plugin_id,
        superclass=superclass,
        config=args,
        policy=policy,
        store_path=store_path,
        data_dir=data_dir,
        core_api=self)

  def _ConfigEntriesToSandboxes(self, superclass, entries):
    plugins = {}
    for plugin_id, plugin_config in entries.items():
      # Parse this particular plugin entry and add to the _plugins map.
      plugin_entry = self._ConfigEntryToSandbox(
          superclass=superclass,
          plugin_id=plugin_id,
          config=plugin_config)
      plugins[plugin_id] = plugin_entry
    return plugins

  def _StartBuffer(self):
    self._buffer.Start(True)
    self._SyncConsumerList()

  def _SyncConsumerList(self):
    """Synchronizes consumer list with buffer."""
    consumers = [plugin.plugin_id for plugin in self._plugins.values()
                 if plugin.GetSuperclass() is plugin_base.OutputPlugin]
    buffer_consumers = list(self._buffer.CallPlugin('ListConsumers'))
    logging.info('Syncing consumer lists')
    logging.debug('Our consumer list: %s', consumers)
    logging.debug('Buffer consumer list: %s', buffer_consumers)
    for c in buffer_consumers:
      if c not in consumers:
        self._buffer.CallPlugin('RemoveConsumer', c)
    for c in consumers:
      if c not in buffer_consumers:
        self._buffer.CallPlugin('AddConsumer', c)

  def Run(self):
    try:
      self._state = STARTING
      self._Start()
      plugin_states = {}
      for plugin in self._plugins.values():
        plugin_states[plugin] = plugin.GetState()
      while self._state not in (STOPPING, DOWN):
        # If Instalog is just starting, check to see that all plugins have left
        # the STARTING state.  When this occurs, Instalog's state should change
        # to UP.
        if (self._state is STARTING and
            all([state is not plugin_sandbox.STARTING
                 for state in plugin_states.values()])):
          self._state = UP
        for plugin in self._plugins.values():
          plugin.AdvanceState()
          if plugin_states[plugin] != plugin.GetState():
            logging.info('Plugin %s changed state from %s to %s',
                         plugin.plugin_id, plugin_states[plugin],
                         plugin.GetState())
          plugin_states[plugin] = plugin.GetState()
        time.sleep(1)
    except Exception as e:
      logging.exception(e)

    # In case there was some error in the Run function (exception or otherwise),
    # call Stop synchronously at the end just in case.
    self.Stop(True)
    logging.warning('Stopped')

  def _Start(self):
    logging.info('Starting buffer...')
    self._StartBuffer()
    logging.info('Started buffer')

    for plugin in self._plugins.values():
      logging.info('Starting %s...', plugin.plugin_id)
      plugin.Start()
    for plugin in self._plugins.values():
      plugin.AdvanceState(True)
      logging.info('Started %s', plugin.plugin_id)

  def IsUp(self):
    with self._rpc_lock:
      return self._state is UP

  def Stop(self, sync=False):
    """Stops Instalog.

    Args:
      sync: If true, only returns when Instalog has stopped running.
    """
    # If called in asynchronous mode, kick off a thread to perform the stop.
    if not sync:
      threading.Thread(target=self.Stop, args=(True,)).start()
      return

    with self._rpc_lock:
      # If Instalog is still starting up, wait for it to finish.
      while self._state is STARTING:
        time.sleep(0.5)

      # Check for _state here just in case of multiple Stop calls.
      if self._state is STOPPING:
        while self._state is not DOWN:
          time.sleep(0.5)
      if self._state is DOWN:
        return

      self._state = STOPPING
      for plugin in self._plugins.values():
        if plugin.IsLoaded():
          logging.info('Stopping %s...', plugin.plugin_id)
          plugin.Stop()

      for plugin in self._plugins.values():
        plugin.AdvanceState(True)
        logging.info('Stopped %s', plugin.plugin_id)

      logging.info('Stopping buffer...')
      self._buffer.Stop(True)
      logging.info('Stopped buffer')
      self._state = DOWN
      self._ShutdownRPCServer()

  def Inspect(self, plugin_id, json_path):
    with self._rpc_lock:
      if plugin_id not in self._plugins:
        return False, 'Plugin `%s\' not found' % plugin_id
      try:
        store_data = self._plugins[plugin_id].store
        return True, json_utils.JSONEncoder().encode(
            json_utils.WalkJSONPath(json_path, store_data))
      except Exception as e:
        return False, ('Error on inspect with JSON path `%s\': %s'
                       % (json_path, str(e)))

  def Flush(self, plugin_id, timeout):
    """Flushes the given plugin with given timeout.

    Args:
      plugin_id: See plugin_sandbox.PluginSandbox.
      timeout: Seconds to wait for flushing the plugin.

    Returns:
      A tuple, where the first element is a boolean to represent success or not,
      and the second element is a dictionary contains 'result',
      'completed_count' and 'total_count'.
    """
    with self._rpc_lock:
      if plugin_id not in self._plugins:
        return False, {'result': 'error (Plugin does not exist)',
                       'completed_count': -1, 'total_count': -1}
      plugin = self._plugins[plugin_id]
      if plugin.GetSuperclass() is not plugin_base.OutputPlugin:
        return False, {'result': 'error (Plugin is not output plugin)',
                       'completed_count': -1, 'total_count': -1}
      if not plugin.Flush(timeout, True):
        progress = plugin.GetProgress()
        return False, {'result': 'timeout', 'completed_count': progress[0],
                       'total_count': progress[1]}
      progress = plugin.GetProgress()
      return True, {'result': 'success', 'completed_count': progress[0],
                    'total_count': progress[1]}

  def GetAllProgress(self, details=0):
    return self._buffer.CallPlugin('ListConsumers', details)

  ############################################################
  # Functions below implement plugin_base.CoreAPI.
  ############################################################

  def Emit(self, plugin, events):
    """Emits given events from the specified plugin.

    Args:
      plugin: PluginSandbox object of plugin performing Emit.
      events: List of events to be emitted.

    Returns:
      True if successful, False if any failure occurred.

    Raises:
      PluginCallError if Buffer fails unexpectedly.
    """
    return self._buffer.CallPlugin('Produce', events)

  def NewStream(self, plugin):
    """Creates a new BufferEventStream for the specified plugin.

    Args:
      plugin: PluginSandbox object requesting BufferEventStream.

    Returns:
      Object implementing plugin_base.BufferEventStream.

    Raises:
      PluginCallError if Buffer fails unexpectedly.
    """
    return self._buffer.CallPlugin('Consume', plugin.plugin_id)

  def GetProgress(self, plugin):
    """Returns the current progress through buffer for the specified plugin.

    Args:
      plugin: PluginSandbox object requesting BufferEventStream.

    Returns:
      A tuple (completed_count, total_count) representing how many Events have
      been processed so far, and how many exist in total.

    Raises:
      PluginCallError if Buffer fails unexpectedly.
    """
    return self._buffer.CallPlugin('ListConsumers')[plugin.plugin_id]

  def GetNodeID(self):
    """Returns the ID of this Instalog node.

    Returns:
      A string representing the ID of this Instalog node.
    """
    return self._node_id
