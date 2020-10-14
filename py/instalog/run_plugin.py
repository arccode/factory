#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs an Instalog plugin at the command-line for testing purposes."""

import json
import logging
import os
import queue
import select
import shutil
import sys
import tempfile
import time

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import time_utils


# If Ctrl+C is hit two times in this time interval, a Stop signal will be sent
# to the plugin.  Otherwise, it will be paused/unpaused.
_DOUBLE_SIGINT_INTERVAL = 0.5

# Plugin's state should be printed after every interval.
_STATUS_UPDATE_INTERVAL = 10

# Amount of time to break after each iteration of main loop.
_MAIN_LOOP_INTERVAL = 1

# Amount of time that select should be used to poll stdin to check for input.
_POLL_STDIN_TIMEOUT = 0.1


class PluginRunnerBufferEventStream(plugin_base.BufferEventStream,
                                    log_utils.LoggerMixin):
  """Simulates a BufferEventStream for PluginRunner."""

  def __init__(self, logger_name, event_queue):
    self.logger = logging.getLogger(logger_name)
    self._event_queue = event_queue
    self._retrieved_events = []
    self._expired = False

  def Next(self):
    try:
      ret = self._event_queue.get(False)
      self._retrieved_events.append(ret)
      self.debug('BufferEventStream.Next: %s', ret)
      return ret
    except queue.Empty:
      self.debug('BufferEventStream.Next: (empty)')
      return None

  def Commit(self):
    if self._expired:
      raise plugin_base.EventStreamExpired
    self.debug('BufferEventStream.Commit %d events: %s',
               len(self._retrieved_events), self._retrieved_events)
    # TODO(kitching): Delete attachment files to simulate buffer.
    self._expired = True
    return True

  def Abort(self):
    if self._expired:
      raise plugin_base.EventStreamExpired
    self.debug('BufferEventStream.Abort %d events: %s',
               len(self._retrieved_events), self._retrieved_events)
    # TODO(kitching): Maybe delete attachment files to simulate buffer.
    self._expired = True


class PluginRunner(plugin_sandbox.CoreAPI, log_utils.LoggerMixin):

  def __init__(self, logger_name, plugin_type, config):
    self.logger = logging.getLogger(logger_name)
    self._plugin_type = plugin_type

    # Data directory and JSON store carry across PluginRunner runs.
    self._data_dir = os.path.join(tempfile.gettempdir(),
                                  'plugin_runner.%s' % plugin_type)
    if not os.path.isdir(self._data_dir):
      os.mkdir(self._data_dir)
    self._store_path = os.path.join(self._data_dir, 'store.json')

    # Attachments directory is deleted when PluginRunner ends.
    self._att_dir = os.path.join(self._data_dir, 'attachments')
    if not os.path.isdir(self._att_dir):
      os.mkdir(self._att_dir)

    self.info('Saving plugin data to: %s', self._data_dir)
    self.info('Saving plugin store to: %s', self._store_path)
    self.info('Saving attachments to: %s', self._att_dir)

    self._event_queue = queue.Queue()
    self._plugin = plugin_sandbox.PluginSandbox(
        plugin_type, config=config, store_path=self._store_path,
        data_dir=self._data_dir, core_api=self)
    self._last_interrupt = 0
    self._last_status_update = time_utils.MonotonicTime()

  def Close(self):
    """Performs any final operations."""
    shutil.rmtree(self._att_dir)

  def _GetNextStdinLine(self):
    """Returns next line of input if available."""
    # TODO(kitching): Currently this function has a bug, where it doesn't always
    #                 provide available data from stdin.  This is due
    #                 select.select claiming there is no more input after
    #                 sys.stdin.readline() is read once.  But this is contrary
    #                 to the examples that I have found online (which use a
    #                 similar loop predicated on select.select).  Figure out a
    #                 better way of reading input.
    rlist, _, _ = select.select([sys.stdin], [], [], _POLL_STDIN_TIMEOUT)
    more_data = True
    if sys.stdin not in rlist:
      return None, more_data
    input_line = sys.stdin.readline().strip()
    if not input_line:
      return None, more_data
    if input_line == 'EOF':
      more_data = False
    return input_line, more_data

  def _GetStdinEvents(self):
    """Returns Event objects queued up in stdin buffer."""
    events = []
    more_data = False
    while True:
      input_line, more_data = self._GetNextStdinLine()
      if input_line is None or not more_data:
        break
      event = None
      try:
        event = datatypes.Event.Deserialize(input_line)
      except Exception as e:
        self.exception(e)
      if event:
        self.debug('_GetStdinEvents: New event: %s', event)
        events.append(event)
      else:
        self.info('_GetStdinEvents: Ignoring bogus input: "%s"',
                  input_line)
    return events, more_data

  def ProcessStdin(self):
    """Processes any events pending in stdin.

    Returns:
      True if there may be more data to process.
      False if stdin no longer has data to process.
    """
    events, more_data = self._GetStdinEvents()
    if events:
      superclass = self._plugin.GetSuperclass()
      if superclass is plugin_base.BufferPlugin:
        self.debug('BufferPlugin: Calling BufferPlugin.Produce')
        result = self._plugin.CallPlugin('Produce', events)
        self.info('BufferPlugin: BufferPlugin.Produce returned: %s',
                  result)
      elif superclass is plugin_base.InputPlugin:
        self.info('InputPlugin: [Ignoring]')
      else:
        self.info('OutputPlugin: Adding to plugin queue')
        for event in events:
          self._event_queue.put(event)
    return more_data

  def FlushBufferConsumer(self):
    """Flushes the buffer for our consumer if the plugin is a BufferPlugin."""
    if self._plugin.GetSuperclass() is plugin_base.BufferPlugin:
      # TODO(kitching): Wrap calls to returned BufferStream somehow.
      buffer_stream = self._plugin.CallPlugin('Consume', '__instalog__')
      while True:
        event = buffer_stream.Next()
        if event is None:
          # No data left.
          break
        print(event.Serialize())
      buffer_stream.Commit()

  def PrintStatusUpdate(self):
    # Should we print a plugin status update?
    if (time_utils.MonotonicTime() - self._last_status_update >=
        _STATUS_UPDATE_INTERVAL):
      self.info('Plugin state: %s', self._plugin.GetState())
      # TODO(chuntsen): Fix pylint error
      # pylint: disable=protected-access
      self.info('Plugin data store: %s', self._plugin._plugin.store)
      self._last_status_update = time_utils.MonotonicTime()

  def HandleKeyboardInterrupt(self, interrupt=False):
    # TODO(kitching): The logic in here is still not fully sound.  Try to fix
    #                 the kinks.
    if interrupt:
      if (time_utils.MonotonicTime() - self._last_interrupt <
          _DOUBLE_SIGINT_INTERVAL):
        self.info('Keyboard interrupt: stop')
        self._last_interrupt = 0
        if self._plugin.GetState() is not plugin_sandbox.STOPPING:
          return False
      else:
        self.info('Keyboard interrupt: press Ctrl+C again to stop')
        self._last_interrupt = time_utils.MonotonicTime()

    elif (self._last_interrupt and time_utils.MonotonicTime() -
          self._last_interrupt >= _DOUBLE_SIGINT_INTERVAL and
          self._plugin.GetState() is not plugin_sandbox.STOPPING):
      self.info('Keyboard interrupt: pause/unpause')
      self._last_interrupt = 0
      self._plugin.TogglePause()
    return True

  def Run(self):
    self.info('Starting plugin...')
    self._plugin.Start(True)

    # If this is a BufferPlugin, make sure we have a Consumer set up to use.
    if self._plugin.GetSuperclass() is plugin_base.BufferPlugin:
      try:
        self._plugin.CallPlugin('AddConsumer', '__instalog__')
      except Exception:
        # TODO(kitching): Catch on correct exception.
        # Consumer already exists.
        pass

    # Main keyboard input loop.
    while self._plugin.IsLoaded():
      try:
        self._plugin.AdvanceState()
        if not self.ProcessStdin():
          break
        self.PrintStatusUpdate()
        self.HandleKeyboardInterrupt()
        self.FlushBufferConsumer()
        sys.stdout.flush()
        time.sleep(_MAIN_LOOP_INTERVAL)
      except KeyboardInterrupt:
        if not self.HandleKeyboardInterrupt(True):
          break
      except IOError:  # Probably a broken pipe.
        break

    # Stop the plugin.
    self._plugin.Stop(True)
    self.Close()

  ############################################################
  # Functions below implement plugin_base.CoreAPI.
  ############################################################

  def Emit(self, plugin, events):
    """See Core.Emit."""
    del plugin
    self.debug('Emit %d events: %s', len(events), events)
    for event in events:
      # Move attachments to a temporary directory to simulate buffer.
      for att_id, att_path in event.attachments.items():
        # Use a filename that contains the original one for clarity.
        tmp_path = file_utils.CreateTemporaryFile(
            prefix=os.path.basename(att_path), dir=self._att_dir)
        # Relocate the attachment and update the event path.
        self.debug('Moving attachment %s --> %s...', att_path, tmp_path)
        shutil.move(att_path, tmp_path)
        event.attachments[att_id] = tmp_path

      # TODO(kitching): May result in `IOError: Broken pipe`.  Investigate
      #                 and fix.
      print(event.Serialize())
    return True

  def NewStream(self, plugin):
    """See Core.NewStream."""
    del plugin
    self.debug('NewStream')
    return PluginRunnerBufferEventStream(self.logger.name, self._event_queue)

  def GetNodeID(self):
    """See Core.GetNodeID."""
    return 'run_plugin'

  def GetProgress(self, plugin):
    raise NotImplementedError


def main(plugin_type=None, config=None):
  """Executes a plugin as a command-line utility for testing purposes.

  - For buffer plugins, the buffer is initialized with one consumer.  Events
    are retrieved from stdin, pushed into the buffer, retrieved through the
    consumer, and printed to stdout.

  - For input plugins, emitted events written to stdout.

  - For output plugins, events are retrieved from stdin.

  Args:
    plugin_type: Type of the plugin that should be started.
    config: Configuration dict of the plugin.  Defaults to an empty dict.
  """
  log_utils.InitLogging(log_utils.GetStreamHandler())

  # If no plugin_type is provided, retrieve from command-line arguments.
  if plugin_type is None:
    if len(sys.argv) <= 1:
      sys.exit('No plugin_type detected')
    plugin_type = sys.argv.pop(1)

  # If no config is provided, retrieve from command-line arguments.
  if config is None:
    config = json.loads(sys.argv.pop(1)) if len(sys.argv) > 1 else {}

  logger = logging.getLogger('%s.plugin_runner' % plugin_type)

  plugin_runner = PluginRunner(logger.name, plugin_type, config)
  plugin_runner.Run()


if __name__ == '__main__':
  main()
