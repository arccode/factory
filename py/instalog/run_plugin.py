#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs an Instalog plugin at the command-line for testing purposes."""

from __future__ import print_function

import json
import logging
import sys
import time

import instalog_common  # pylint: disable=W0611
from instalog import plugin_sandbox


# If Ctrl+C is hit two times in this time interval, a Stop signal will be sent
# to the plugin.  Otherwise, it will be paused/unpaused.
_DOUBLE_SIGINT_INTERVAL = 0.5

# Plugin's state should be printed after every interval.
_STATUS_UPDATE_INTERVAL = 5


class RunPluginCore(plugin_sandbox.CoreAPI):
  """Defines the Core API for plugins started by run_plugin.py."""

  def GetStateDir(self, plugin):
    """See Core.GetStateDir."""
    raise NotImplementedError

  def Emit(self, plugin, events):
    """See Core.Emit."""
    logging.info('Emitting events: %s', events)

  def NewStream(self, plugin):
    """See Core.NewStream."""
    raise NotImplementedError


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
  logging.basicConfig(
      level=logging.DEBUG,
      format=LOG_FORMAT)

  # If no plugin_type is provided, retrieve from command-line arguments.
  if plugin_type is None:
    if len(sys.argv) <= 1:
      sys.exit('No plugin_type detected')
    plugin_type = sys.argv.pop(1)

  # If no config is provided, retrieve from command-line arguments.
  if config is None:
    config = json.loads(sys.argv.pop(1)) if len(sys.argv) > 1 else {}

  c = RunPluginCore()
  p = plugin_sandbox.PluginSandbox(plugin_type, config=config, core_api=c)

  logging.info('Starting plugin...')
  p.Start()

  # Main keyboard input loop.
  last_interrupt = 0
  last_status_update = time.time()
  while p.IsLoaded():
    p.AdvanceState()
    # Should we print a plugin status update?
    if time.time() - last_status_update >= _STATUS_UPDATE_INTERVAL:
      logging.info('Plugin state: %s', p.GetState())
      last_status_update = time.time()

    # Manage keyboard interrupts.
    try:
      time.sleep(_DOUBLE_SIGINT_INTERVAL)
      if last_interrupt >= _DOUBLE_SIGINT_INTERVAL:
        logging.info('Keyboard interrupt: pause/unpause')
        last_interrupt = 0
        p.TogglePause()
    except KeyboardInterrupt:
      if time.time() - last_interrupt < _DOUBLE_SIGINT_INTERVAL:
        logging.info('Keyboard interrupt: stop')
        last_interrupt = 0
        p.Stop()
      else:
        logging.info('Keyboard interrupt: press Ctrl+C again to stop')
        last_interrupt = time.time()


if __name__ == '__main__':
  main()
