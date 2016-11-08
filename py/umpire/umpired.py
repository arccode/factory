#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpired implementation.

This is a minimalist umpired implementation.
"""

import glob
import logging
import optparse
import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import init
from cros.factory.umpire import common
from cros.factory.umpire import daemon
from cros.factory.umpire import rpc_cli
from cros.factory.umpire import rpc_dut
from cros.factory.umpire import umpire_env
from cros.factory.umpire import webapp_resourcemap


def StartServer(test_mode=False, config_file=None):
  """Starts Umpire daemon.

  Args:
    test_mode: True to enable test mode.
    config_file: If specified, uses it as config file.
  """
  real_daemon_path = os.path.realpath(__file__)
  # Instanciate environment and load default configuration file.
  env = umpire_env.UmpireEnv()
  if test_mode:
    test_base_dir = os.path.join(os.path.dirname(real_daemon_path), 'testdata')
    if not os.path.isdir(test_base_dir):
      raise common.UmpireError(
          'Test directory %s does not exist. Test mode failed.' % test_base_dir)
    env.base_dir = test_base_dir

  # Make sure that the environment for running the daemon is set.
  init.Init(env, local=False, user='root', group='root')

  env.LoadConfig(custom_path=config_file)

  if env.config is None:
    raise common.UmpireError('Umpire config was not loaded.')

  # Remove runtime pid files before start the server
  logging.info('remove pid files under %s', env.pid_dir)
  for pidfile in glob.glob(os.path.join(env.pid_dir, '*.pid')):
    logging.info('removing pid file: %s', pidfile)
    os.remove(pidfile)
  # Instanciate Umpire daemon and set command handlers and webapp handler.
  umpired = daemon.UmpireDaemon(env)
  # Add command line handlers.
  cli_commands = rpc_cli.CLICommand(env)
  umpired.AddMethodForCLI(cli_commands)
  # Add root RPC handlers.
  root_dut_rpc = rpc_dut.RootDUTCommands(env)
  umpired.AddMethodForDUT(root_dut_rpc)
  # Add Umpire RPC handlers.
  umpire_dut_rpc = rpc_dut.UmpireDUTCommands(env)
  umpired.AddMethodForDUT(umpire_dut_rpc)
  # Add log RPC handlers.
  log_dut_rpc = rpc_dut.LogDUTCommands(env)
  umpired.AddMethodForDUT(log_dut_rpc)
  # Add web applications.
  resourcemap_webapp = webapp_resourcemap.ResourceMapApp(env)
  umpired.AddWebApp(resourcemap_webapp.GetPathInfo(), resourcemap_webapp)
  # Start listening to command port and webapp port.
  umpired.Run()


def main():
  logging.basicConfig(
      level=logging.DEBUG,
      format=('%(asctime)s %(levelname)s %(filename)s %(funcName)s:%(lineno)d '
              '%(message)s'))
  parser = optparse.OptionParser()
  parser.add_option(
      '-t', '--test', dest='test_mode', action='store_true', default=False,
      help='test run testdata/umpired_test.yaml')
  parser.add_option(
      '-c', '--config', dest='config_file', help='path to UmpireConfig file')
  (options, unused_args) = parser.parse_args()
  StartServer(test_mode=options.test_mode, config_file=options.config_file)


if __name__ == '__main__':
  main()
