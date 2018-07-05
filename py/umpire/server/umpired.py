#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpired implementation.

This is a minimalist umpired implementation.
"""

import glob
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import daemon
from cros.factory.umpire.server import migrate
from cros.factory.umpire.server import rpc_cli
from cros.factory.umpire.server import rpc_dut
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import webapp_download_slots
from cros.factory.umpire.server import webapp_resourcemap


def StartServer():
  """Starts Umpire daemon."""
  migrate.RunMigrations()

  # Instantiate environment and load default configuration file.
  env = umpire_env.UmpireEnv()
  env.LoadConfig()

  # Remove runtime pid files before start the server
  logging.info('remove pid files under %s', env.pid_dir)
  for pidfile in glob.glob(os.path.join(env.pid_dir, '*.pid')):
    logging.info('removing pid file: %s', pidfile)
    os.remove(pidfile)

  # Instantiate Umpire daemon and set command handlers and webapp handler.
  umpired = daemon.UmpireDaemon(env)
  # Add command line handlers.
  cli_commands = rpc_cli.CLICommand(umpired)
  umpired.AddMethodForCLI(cli_commands)
  # Add root RPC handlers.
  root_dut_rpc = rpc_dut.RootDUTCommands(umpired)
  umpired.AddMethodForDUT(root_dut_rpc)
  # Add Umpire RPC handlers.
  umpire_dut_rpc = rpc_dut.UmpireDUTCommands(umpired)
  umpired.AddMethodForDUT(umpire_dut_rpc)
  # TODO(hungte) Change shopfloor service to a real Umpire service.
  # Add Shopfloor Service RPC handlers
  shopfloor_service_rpc = rpc_dut.ShopfloorServiceDUTCommands(umpired)
  umpired.AddMethodForDUT(shopfloor_service_rpc)
  # Add log RPC handlers.
  log_dut_rpc = rpc_dut.LogDUTCommands(umpired)
  umpired.AddMethodForDUT(log_dut_rpc)
  # Add web applications.
  resourcemap_webapp = webapp_resourcemap.ResourceMapApp(env)
  umpired.AddWebApp(resourcemap_webapp.GetPathInfo(), resourcemap_webapp)
  download_slots_webapp = webapp_download_slots.DownloadSlotsApp(env)
  umpired.AddWebApp(download_slots_webapp.GetPathInfo(), download_slots_webapp)
  # Start listening to command port and webapp port.
  umpired.Run()


def main():
  logging.basicConfig(
      level=logging.DEBUG,
      format=('%(asctime)s %(levelname)s %(filename)s %(funcName)s:%(lineno)d '
              '%(message)s'))
  StartServer()


if __name__ == '__main__':
  main()
