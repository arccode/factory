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
from twisted.internet import reactor

import factory_common # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher import ShopFloorLauncherException
from cros.factory.shopfloor.launcher import utils
from cros.factory.shopfloor.launcher.commands import LauncherCommandFactory


# The string for detecting if we're inside a .par file
_RESOURCE_FACTORY_PAR = '/resources/factory.par'


def Stop():
  utils.StopServices()


def Run(config_file):
  """ShopFloor daemon loop."""
  utils.UpdateConfig(config_file)
  logging.info('Command port: %d', constants.COMMAND_PORT)
  reactor.listenTCP(constants.COMMAND_PORT, LauncherCommandFactory())
  reactor.addSystemEventTrigger('before', 'shutdown', Stop)
  reactor.run()


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


if __name__ == '__main__':
  main()

