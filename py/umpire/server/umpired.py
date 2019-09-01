#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpired implementation."""

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
  umpired.AddMethodForCLI(rpc_cli.CLICommand(umpired))
  # Add root RPC handlers.
  umpired.AddMethodForDUT(rpc_dut.RootDUTCommands(umpired))
  # Add Umpire RPC handlers.
  umpired.AddMethodForDUT(rpc_dut.UmpireDUTCommands(umpired))
  # TODO(hungte) Change shopfloor service to a real Umpire service.
  # Add Shopfloor Service RPC handlers
  umpired.AddMethodForDUT(rpc_dut.ShopfloorServiceDUTCommands(umpired))
  # Add log RPC handlers.
  umpired.AddMethodForDUT(rpc_dut.LogDUTCommands(umpired))
  # Add web applications.
  umpired.AddWebApp(
      webapp_resourcemap.PATH_INFO, webapp_resourcemap.ResourceMapApp(env))
  umpired.AddWebApp(
      webapp_download_slots.PATH_INFO,
      webapp_download_slots.DownloadSlotsApp())
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
