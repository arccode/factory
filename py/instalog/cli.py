#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import argparse
import logging
import os
import signal
import sys
import threading

import instalog_common  # pylint: disable=unused-import
from instalog import core
from instalog import daemon_utils
from instalog import log_utils
from instalog.utils import sync_utils
from instalog.utils import type_utils

from instalog.external import jsonrpclib
from instalog.external import yaml


# The default number of seconds to wait before giving up on a flush.
_DEFAULT_FLUSH_TIMEOUT = 30
_DEFAULT_STOP_TIMEOUT = 10


class InstalogService(daemon_utils.Daemon):
  """Represents the Instalog daemon service."""

  def __init__(self, config, logging_level):
    self._config = config
    self._logging_level = logging_level
    self._core = None
    super(InstalogService, self).__init__(
        pidfile=config['instalog']['pid_file'])

  def _SignalHandler(self, signal_num, frame):
    """Signal handler to stop Instalog on SIGINT or SIGTERM."""
    del frame
    logging.debug('_SignalHandler called with signalnum=%s', signal_num)
    if signal_num not in [signal.SIGINT, signal.SIGTERM]:
      return
    if self._core:
      # No need for a lock since _SignalHandler will only ever be called from
      # Instalog's main thread.
      signal_string = 'SIGINT' if signal_num == signal.SIGINT else 'SIGTERM'
      logging.warning('%s detected, stopping', signal_string)
      self._core.Stop()
      self._core = None

  def _InitLogging(self):
    """Sets up logging."""
    # TODO(kitching): Refactor (some of) this code to log_utils module.
    # Get logger.
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # In certain situations, a StreamHandler to stdout is created implicitly.
    # Since we want to create our own, we need to remove the default one if it
    # exists.
    if logger.handlers:
      logger.removeHandler(logger.handlers[0])

    # Create formatter.
    formatter = logging.Formatter(log_utils.LOG_FORMAT)

    # Save logging calls to log file.
    fh = logging.FileHandler(self._config['instalog']['log_file'])
    fh.setFormatter(formatter)
    fh.setLevel(self._logging_level)
    logger.addHandler(fh)

    # Output logging calls to console (for when foreground=True).
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    sh.setLevel(self._logging_level)
    logger.addHandler(sh)

  def Run(self, foreground):
    """Starts Instalog."""
    self._InitLogging()

    signal.signal(signal.SIGINT, self._SignalHandler)
    signal.signal(signal.SIGTERM, self._SignalHandler)

    self._core = core.Instalog(
        node_id=self._config['instalog']['node_id'],
        data_dir=self._config['instalog']['data_dir'],
        cli_hostname=self._config['instalog']['cli_hostname'],
        cli_port=self._config['instalog']['cli_port'],
        buffer_plugin=self._config['buffer'],
        input_plugins=self._config['input'],
        output_plugins=self._config['output'])
    self._core.Run()


class InstalogCLI(object):
  """Represents the CLI interface used to control Instalog."""

  def __init__(self, args):
    # Read config file.
    config_path = self._LocateConfigFile(args.config)
    if config_path is None:
      exit('No config file found')
    with open(config_path) as f:
      config = yaml.load(f)

    # logging.WARNING = 30, logging.INFO = 20, logging.DEBUG = 10
    logging_level = logging.INFO - ((args.verbose - args.quiet) * 10)

    self._service = InstalogService(config, logging_level)
    self._core = jsonrpclib.Server(
        'http://%s:%s' % (config['instalog']['cli_hostname'],
                          config['instalog']['cli_port']))

    if args.cmd == 'start':
      self.Start(args.foreground)
    elif args.cmd == 'stop':
      self.Stop(args.timeout)
    elif args.cmd == 'restart':
      self.Restart()
    elif args.cmd == 'status':
      self.Status()
    elif args.cmd == 'inspect':
      self.Inspect(args.plugin_id, args.json_path)
    elif args.cmd == 'flush':
      self.Flush(args.plugin_id, args.timeout)


  def _LocateConfigFile(self, user_path):
    """Locates the config file that should be used by Instalog."""
    if user_path:
      return user_path
    paths = [
        os.path.join(os.getcwd(), 'instalog.yaml'),
        os.path.join(os.path.dirname(os.path.realpath(__file__)),
                     'instalog.yaml'),
        os.path.join(os.path.expanduser('~'), '.instalog.yaml'),
        os.path.join(os.sep, 'etc', 'instalog.yaml'),
        os.path.join(os.sep, 'run', 'instalog.yaml')]
    for path in paths:
      logging.debug('Checking %s for config file...', path)
      if os.path.exists(path):
        logging.info('Config file found at %s', path)
        return path

  def Restart(self):
    """Restarts the daemon."""
    self.Stop(_DEFAULT_STOP_TIMEOUT)
    self.Start(False)

  def Start(self, foreground):
    """Starts the daemon.

    Args:
      foreground: Does not detach the daemon.
    """
    print('Starting...')
    self._service.Start(foreground)
    if foreground:
      return

    # First, wait for the daemon process to start.
    try:
      sync_utils.WaitFor(self._service.IsRunning, 10)
    except type_utils.TimeoutError:
      print('Daemon could not be brought up, check the logs')
      sys.exit(1)

    def TryIsUp():
      try:
        # Perform the real check to see if Instalog is up internally.
        return self._core.IsUp()
      except Exception:
        raise type_utils.TimeoutError('Could not call core IsUp')

    try:
      if sync_utils.WaitFor(TryIsUp, 10):
        print('DONE')
        return
    except type_utils.TimeoutError:
      pass
    print('Daemon could not be brought up, check the logs')
    sys.exit(1)

  def Stop(self, timeout):
    """Stops the daemon."""
    # First, send the "stop" instruction to the daemon.
    print('Stopping...')
    try:
      self._core.Stop()
    except Exception:
      print('Could not connect to daemon, is it running?')
      sys.exit(1)

    # Then, wait for the process to come down.
    try:
      sync_utils.WaitFor(self._service.IsStopped, timeout)
    except type_utils.TimeoutError:
      print('Still shutting down?')
      sys.exit(1)
    else:
      print('DONE')

  def Status(self):
    """Prints the status of the daemon."""
    running = self._service.IsRunning()
    if running:
      up = self._core.IsUp()
      print('UP' if up else 'STARTING')
    else:
      print('DOWN')

  def Inspect(self, plugin_id, json_path):
    """Inspects the store of a given plugin."""
    success, value = self._core.Inspect(plugin_id, json_path)
    print(value)
    if not success:
      sys.exit(1)

  def Flush(self, plugin_id, timeout):
    """Flushes the given plugin with given timeout."""
    success, value = self._core.Flush(plugin_id, timeout)
    print(value)
    if not success:
      sys.exit(1)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--config', '-c',
      help='config file path; by default, searches: \n'
           '$PWD/instalog.yaml py/instalog/instalog.yaml '
           '~/.instalog.yaml /etc/instalog.yaml /run/instalog.yaml')
  parser.add_argument(
      '--verbose', '-v', action='count', default=0,
      help='increase verbosity')
  parser.add_argument(
      '--quiet', '-q', action='count', default=0,
      help='decrease verbosity')

  subparsers = parser.add_subparsers(title='commands')

  start_parser = subparsers.add_parser('start', help='start Instalog')
  start_parser.set_defaults(cmd='start')
  start_parser.add_argument(
      '--no-daemon', '-n', dest='foreground', action='store_true',
      help='keep in foreground')

  stop_parser = subparsers.add_parser('stop', help='stop Instalog')
  stop_parser.set_defaults(cmd='stop')
  stop_parser.add_argument(
      '--timeout', '-w', type=float,
      required=False, default=_DEFAULT_STOP_TIMEOUT,
      help='time to wait before giving up')

  restart_parser = subparsers.add_parser('restart', help='restart Instalog')
  restart_parser.set_defaults(cmd='restart')

  status_parser = subparsers.add_parser('status', help='print Instalog status')
  status_parser.set_defaults(cmd='status')

  inspect_parser = subparsers.add_parser('inspect', help='inspect plugin store')
  inspect_parser.set_defaults(cmd='inspect')
  inspect_parser.add_argument(
      'plugin_id', type=str, help='ID of plugin to inspect')
  inspect_parser.add_argument(
      'json_path', type=str, nargs='?', default='.',
      help='path of store JSON to print')

  flush_parser = subparsers.add_parser('flush', help='flush plugin')
  flush_parser.set_defaults(cmd='flush')
  flush_parser.add_argument(
      '--timeout', '-w', type=float,
      required=False, default=_DEFAULT_FLUSH_TIMEOUT,
      help='time to wait before giving up')
  flush_parser.add_argument(
      'plugin_id', type=str, nargs='?', default=None,
      help='ID of plugin to flush')

  args = parser.parse_args()

  InstalogCLI(args)
