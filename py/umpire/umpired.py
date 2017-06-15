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
from cros.factory.umpire import common
from cros.factory.umpire import daemon
from cros.factory.umpire import resource
from cros.factory.umpire import rpc_cli
from cros.factory.umpire import rpc_dut
from cros.factory.umpire import umpire_env
from cros.factory.umpire import webapp_resourcemap
from cros.factory.utils import file_utils


# Relative path of Umpire CLI / Umpired in toolkit directory.
_UMPIRE_CLI_IN_TOOLKIT_PATH = os.path.join('bin', 'umpire')
_DEFAULT_CONFIG_NAME = 'default_umpire.yaml'


def InitDaemon(env, root_dir='/'):
  """Initializes an Umpire working environment.

  It creates base directory (specified in env.base_dir) and sets up daemon
  running environment.

  Args:
    env: UmpireEnv object.
    root_dir: Root directory. Used for testing purpose.
  """
  def SetUpDir():
    """Sets up Umpire directory structure.

    It figures out Umpire base dir, creates it and its sub directories.
    """
    def TryMkdir(path):
      if not os.path.isdir(path):
        os.makedirs(path)

    TryMkdir(env.base_dir)
    for sub_dir in env.SUB_DIRS:
      TryMkdir(os.path.join(env.base_dir, sub_dir))

  def SymlinkBinary():
    """Creates symlink to umpire executable.

    It symlinks /usr/local/bin/umpire to $toolkit_base/bin/umpire.

    Note that root '/'  can be overridden by arg 'root_dir' for testing.
    """
    umpire_binary = os.path.join(
        env.server_toolkit_dir, _UMPIRE_CLI_IN_TOOLKIT_PATH)
    default_symlink = os.path.join(root_dir, 'usr', 'local', 'bin', 'umpire')

    if not os.path.lexists(default_symlink):
      os.symlink(umpire_binary, default_symlink)
      logging.info('Symlink %r -> %r', default_symlink, umpire_binary)

  def InitConfig():
    """Prepares the very first UmpireConfig and PayloadConfig, and marks the
    UmpireConfig as active.

    An active config is necessary for the second step, import-bundle.
    """
    env.AddConfigFromBlob('{}', resource.ConfigTypeNames.payload_config)

    # Do not override existing active config.
    if not os.path.exists(env.active_config_file):
      template_path = os.path.join(env.server_toolkit_dir, _DEFAULT_CONFIG_NAME)
      config_in_resource = env.GetResourcePath(
          env.AddConfig(template_path, resource.ConfigTypeNames.umpire_config))
      file_utils.SymlinkRelative(config_in_resource, env.active_config_file,
                                 base=env.base_dir)
      logging.info('Init UmpireConfig %r and set it as active.',
                   config_in_resource)

  logging.info('Init umpire to %r', env.base_dir)

  SetUpDir()
  InitConfig()
  SymlinkBinary()


def StartServer(config_file=None):
  """Starts Umpire daemon.

  Args:
    test_mode: True to enable test mode.
    config_file: If specified, uses it as config file.
  """
  # Instantiate environment and load default configuration file.
  env = umpire_env.UmpireEnv()

  # Make sure that the environment for running the daemon is set.
  InitDaemon(env)

  env.LoadConfig(custom_path=config_file)

  if env.config is None:
    raise common.UmpireError('Umpire config was not loaded.')

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
  shopfloor_service_rpc = rpc_dut.ShopfloorServiceDUTCommands(
      umpired, env.shopfloor_service_url)
  umpired.AddMethodForDUT(shopfloor_service_rpc)
  # Add log RPC handlers.
  log_dut_rpc = rpc_dut.LogDUTCommands(umpired)
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
      '-c', '--config', dest='config_file', help='path to UmpireConfig file')
  (options, unused_args) = parser.parse_args()
  StartServer(config_file=options.config_file)


if __name__ == '__main__':
  main()
