#!/usr/bin/env python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Python twisted's module creates definition dynamically  7
# pylint: disable=E1101

"""Shopfloor daemon.

The launcher is a daemon that manages underlying services. Including HTTPD
frontend, Shopfloor server FastCGI, update server and log minitor service.

Example:
  # Run the daemon in user mode with test data set
  ./shopfloord.py -t
"""


import logging
import optparse
import os
import signal
from twisted.internet import error
from twisted.internet import reactor

import factory_common # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher import ShopFloorLauncherException
from cros.factory.shopfloor.launcher import utils
from cros.factory.shopfloor.launcher.commands import LauncherCommandFactory


# The string for detecting if we're inside a .par file
_RESOURCE_FACTORY_PAR = '/resources/factory.par'


def Run(config_file):
  """ShopFloor daemon loop."""
  utils.UpdateConfig(config_file)
  logging.info('Command port: %d', constants.COMMAND_PORT)
  reactor.listenTCP(constants.COMMAND_PORT, LauncherCommandFactory())
  # Start twisted, and prevent reactor from install signal handlers.
  reactor.run(installSignalHandlers=0)


def main():
  parser = optparse.OptionParser()

  parser.add_option('-c', '--config', dest='yaml_config',
                    default='shopfloor.yaml')
  parser.add_option('-t', '--test', dest='test_run', action='store_true',
                    default=False)
  parser.add_option('-l', '--local', dest='local_dir', action='store_true',
                    default=False)

  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  log_format = '%(asctime)s %(levelname)s '
  log_verbosity = logging.INFO
  if options.test_run:
    log_format += '(%(filename)s:%(lineno)d) '
    log_verbosity = logging.DEBUG
  log_format += '%(message)s'

  logging.basicConfig(level=log_verbosity, format=log_format)

  server_path = os.path.realpath(__file__)

  search_dirs = []
  # Set runtime_dir when running locally.
  if options.test_run and not server_path.startswith(
      constants.SHOPFLOOR_INSTALL_DIR):
    if _RESOURCE_FACTORY_PAR in server_path:
      env.runtime_dir = server_path[0:server_path.index(_RESOURCE_FACTORY_PAR)]
    else:
      env.runtime_dir = os.path.join(os.path.dirname(server_path), 'testdata')
    search_dirs.append(os.path.dirname(server_path))

  search_dirs += [env.runtime_dir, env.GetResourcesDir()]
  config_file = utils.SearchFile(options.yaml_config, search_dirs)
  if config_file and os.path.isfile(config_file):
    Run(config_file)
  else:
    raise ShopFloorLauncherException('Launcher YAML config file not found: %s' %
                                     options.yaml_config)


def ReactorStop():
  """Forces reactor to stop."""
  logging.info('Stopping reactor.')
  try:
    reactor.stop()
  except error.ReactorNotRunning:
    pass


def DelayedStop(count_down):
  """Waits for services to end and stops the reactor.

  Args:
    count_down: seconds to wait before force shutdown.
  """
  # Forces stop when count to zero
  if count_down <= 0:
    ReactorStop()

  for svc in env.launcher_services:
    if svc.subprocess:
      logging.info('Wait for %s ... %d', svc.name, count_down)
      reactor.callLater(1, DelayedStop, count_down - 1)
  ReactorStop()


def SignalHandler(sig, dummy_frame):
  """Initiates stopping sequence.

  Launcher holds multiple subprocess, runs the event loop in twisted reactor,
  hence it could not stop gracefully with system before shutdown handler. The
  correct sequence is:
    SIG[TERM|INT]
        --> stop subprocesses (call utils.StopServices())
        --> wait for subprocesses end (reactor.callLater())
        --> stop reactor and ignore not running error.
  """
  logging.info('Received signal %d', sig)
  logging.info('Stopping system...')
  utils.StopServices()
  reactor.callLater(3, DelayedStop, 60)


if __name__ == '__main__':
  signal.signal(signal.SIGTERM, SignalHandler)
  signal.signal(signal.SIGINT, SignalHandler)
  main()

