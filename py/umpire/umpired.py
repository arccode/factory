#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpired implementation.

This is a minimalist umpired implementation.
"""

import logging
import optparse
import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import rpc_dut
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.rpc_cli import CLICommand
from cros.factory.umpire.daemon import UmpireDaemon
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.umpire.webapp_resourcemap import ResourceMapApp


# This template file is from private overlay.
TEMPLATE_YAML = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'umpired_template.yaml')


def StartServer(testmode=False, config_file=TEMPLATE_YAML):
  # Instanciate environment and load default configuration file
  env = UmpireEnv()
  if testmode:
    (test_base_dir, _) = os.path.split(
        os.path.realpath(__file__))
    test_base_dir = os.path.join(test_base_dir, 'testdata')
    if not os.path.isdir(test_base_dir):
      raise UmpireError('Dir %s does not exist. Test mode failed.' %
                        test_base_dir)
    env.base_dir = test_base_dir
  env.LoadConfig(custom_path=config_file)

  if env.config is None:
    raise UmpireError('Umpire config was not loaded.')

  # Instanciate Umpire daemon and set command handlers and webapp handler
  umpired = UmpireDaemon(env)
  # Add command line handlers
  cli_commands = CLICommand(env)
  umpired.AddMethodForCLI(cli_commands)
  # Add root RPC handlers
  root_dut_rpc = rpc_dut.RootDUTCommands(env)
  umpired.AddMethodForDUT(root_dut_rpc)
  # Add Umpire RPC handlers
  umpire_dut_rpc = rpc_dut.UmpireDUTCommands(env)
  umpired.AddMethodForDUT(umpire_dut_rpc)
  # Add log RPC handlers
  log_dut_rpc = rpc_dut.LogDUTCommands(env)
  umpired.AddMethodForDUT(log_dut_rpc)
  # Add web applications
  resourcemap_webapp = ResourceMapApp(env)
  umpired.AddWebApp(resourcemap_webapp.GetPathInfo(), resourcemap_webapp)
  # Start listening to command port and webapp port
  umpired.Run()


def main():
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(asctime)s %(levelname)s %(message)s')
  parser = optparse.OptionParser()
  parser.add_option(
      '-t', '--test', dest='testmode', action='store_true', default=False,
      help='test run testdata/umpired_test.yaml')
  parser.add_option(
      '-y', '--yaml', dest='custom_path', default=TEMPLATE_YAML,
      help='use another test yaml config file')
  (options, unused_args) = parser.parse_args()
  StartServer(testmode=options.testmode, config_file=options.custom_path)


if __name__ == '__main__':
  main()
