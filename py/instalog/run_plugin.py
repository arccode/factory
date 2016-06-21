#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs an Instalog plugin at the command-line for testing purposes."""

from __future__ import print_function

import json
import logging
import Queue
import select
import sys
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog import plugin_sandbox


# If Ctrl+C is hit two times in this time interval, a Stop signal will be sent
# to the plugin.  Otherwise, it will be paused/unpaused.
_DOUBLE_SIGINT_INTERVAL = 0.5

# Plugin's state should be printed after every interval.
_STATUS_UPDATE_INTERVAL = 5

# Amount of time that select should be used to poll stdin to check for input.
_POLL_STDIN_TIMEOUT = 0.1


class RunPluginCore(plugin_sandbox.CoreAPI):
  """Defines the Core API for plugins started by run_plugin.py."""

  def __init__(self, logger):
    self.logger = logger
    # Event queue for output plugins.
    self._event_queue = Queue.Queue()

  def AddEvent(self, event):
    self._event_queue.put(event)

  def GetStateDir(self, plugin):
    """See Core.GetStateDir."""
    raise NotImplementedError

  def Emit(self, plugin, events):
    """See Core.Emit."""
    self.logger.info('Emit for events: %s', events)
    for event in events:
      print(event.Serialize())

  def NewStream(self, plugin):
    """See Core.NewStream."""
    self.logger.info('NewStream')
    return RunPluginBufferEventStream(self.logger, self._event_queue)


class RunPluginBufferEventStream(plugin_base.BufferEventStream):
  """Simulates a buffer event stream for RunPluginCore."""

  def __init__(self, logger, event_queue):
    self.logger = logger
    self._event_queue = event_queue
    self._retrieved_events = []

  def Next(self):
    try:
      ret = self._event_queue.get(False)
      self._retrieved_events.append(ret)
      self.logger.info('Next for event: %s', ret)
      return ret
    except Queue.Empty:
      self.logger.info('Next (empty)')
      return None

  def Commit(self):
    self.logger.info('Commit for events: %s', self._retrieved_events)

  def Abort(self):
    self.logger.info('Abort for events: %s', self._retrieved_events)


class PluginRunner(object):

  def __init__(self, logger, plugin_type, config):
    self.logger = logger
    self._core = RunPluginCore(logger)
    self._plugin = plugin_sandbox.PluginSandbox(
        plugin_type, config=config, core_api=self._core)
    self._last_interrupt = 0
    self._last_status_update = time.time()
    self._current_attachments = {}

  def _GetInputLine(self):
    # User input for output plugins.
    rlist, _, _ = select.select([sys.stdin], [], [], _POLL_STDIN_TIMEOUT)
    if not rlist:
      return None
    user_input = sys.stdin.readline().strip()
    if not user_input:
      return None
    return user_input

  def ProcessStdin(self):
    user_input = self._GetInputLine()
    if user_input == 'EOF':
      return False
    if user_input is None:
      return True

    # Assume this is a JSON event.
    event = None
    try:
      if user_input.startswith('{'):
        event = datatypes.Event.DeserializeRaw(user_input, attachments={})
      elif user_input.startswith('['):
        event = datatypes.Event.Deserialize(user_input)
    except Exception as e:
      self.logger.exception(e)

    # Process the event.
    if event:
      self.logger.info('New event: %s', event)
      self._core.AddEvent(event)
    else:
      self.logger.info('Ignoring bogus input: "%s"', user_input)
    return True

  def PrintStatusUpdate(self):
    # Should we print a plugin status update?
    if time.time() - self._last_status_update >= _STATUS_UPDATE_INTERVAL:
      self.logger.info('Plugin state: %s', self._plugin.GetState())
      self._last_status_update = time.time()

  def HandleKeyboardInterrupt(self, interrupt=False):
    # TODO(kitching): The logic in here is still not fully sound.  Try to fix
    #                 the kinks.
    if interrupt:
      if time.time() - self._last_interrupt < _DOUBLE_SIGINT_INTERVAL:
        self.logger.info('Keyboard interrupt: stop')
        self._last_interrupt = 0
        if self._plugin.GetState() is not plugin_sandbox.STOPPING:
          self._plugin.Stop()
      else:
        self.logger.info('Keyboard interrupt: press Ctrl+C again to stop')
        self._last_interrupt = time.time()

    elif (self._last_interrupt and
          time.time() - self._last_interrupt >= _DOUBLE_SIGINT_INTERVAL and
          self._plugin.GetState() is not plugin_sandbox.STOPPING):
      self.logger.info('Keyboard interrupt: pause/unpause')
      self._last_interrupt = 0
      self._plugin.TogglePause()

  def Main(self):
    self.logger.info('Starting plugin...')
    self._plugin.Start(True)

    # Main keyboard input loop.
    while self._plugin.IsLoaded():
      try:
        self._plugin.AdvanceState()
        if not self.ProcessStdin():
          self._plugin.Stop(True)
        self.PrintStatusUpdate()
        self.HandleKeyboardInterrupt()
        sys.stdout.flush()
        time.sleep(0.001)
      except KeyboardInterrupt:
        self.HandleKeyboardInterrupt(True)
      except IOError:  # Probably a broken pipe.
        self._plugin.Stop(True)


def main(plugin_type=None, config=None):
  """Executes a plugin as a command-line utility for testing purposes.

  - For buffer plugins, the buffer is initialized with one consumer.  Events
    are retrieved from stdin, pushed into the buffer, retrieved through the
    consumer, and printed to stdout.

  - For input plugins, emitted events are displayed via Python logging.

  - For output plugins, events are retrieved from stdin.

  Args:
    plugin_type: Type of the plugin that should be started.
    config: Configuration dict of the plugin.  Defaults to an empty dict.
  """
  LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
  logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

  # If no plugin_type is provided, retrieve from command-line arguments.
  if plugin_type is None:
    if len(sys.argv) <= 1:
      sys.exit('No plugin_type detected')
    plugin_type = sys.argv.pop(1)

  # If no config is provided, retrieve from command-line arguments.
  if config is None:
    config = json.loads(sys.argv.pop(1)) if len(sys.argv) > 1 else {}

  logger = logging.getLogger('%s.plugin_runner' % plugin_type)

  plugin_runner = PluginRunner(logger, plugin_type, config)
  plugin_runner.Main()


if __name__ == '__main__':
  main()
