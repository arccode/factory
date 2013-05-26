#!/usr/bin/env python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Python twisted's module creates definition dynamically  7
# pylint: disable=E1101

"""Shopfloor command line utility

This utility packs command line argument list sys.argv and current working dir
into a single line JSON command string. Shopfloor launcher listens to command
port (default: 8084, defined in constants.py) and returns human readible
text output.

Examples:
  # Display current running configuration
  shopfloor info
  # Import a factory bundle
  shopfloor import <resource_filename>
  # Deploy a newly imported configuration
  shopfloor deploy shopfloor.yaml#54311e9a
"""


import glob
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import yaml
from twisted.internet import error
from twisted.internet import reactor
from twisted.internet.protocol import Protocol
from twisted.internet.protocol import ClientFactory

import factory_common  # pylint: disable=W0611
from cros.factory.hacked_argparse import CmdArg
from cros.factory.hacked_argparse import Command
from cros.factory.hacked_argparse import ParseCmdline
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher import importer
from cros.factory.shopfloor.launcher import ShopFloorLauncherException
from cros.factory.shopfloor.launcher import utils
from cros.factory.shopfloor.launcher import yamlconf
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import OpenDevNull
from cros.factory.utils.process_utils import SpawnOutput


PID_FILE = 'shopfloord.pid'
LOG_FILE = 'shopfloord.log'
FACTORY_SOFTWARE = 'factory.par'
PREV_FACTORY_SOFTWARE = 'factory.par.prev'
CONFIG_FILE = 'shopfloor.yaml'
PREV_CONFIG_FILE = 'shopfloor.yaml.prev'
SHOPFLOOR_UTIL = 'shopfloor'
SHOPFLOOR_DAEMON = 'shopfloord'


def StopReactor():
  """Stops reactor to exit cleanly."""
  try:
    reactor.stop()
  except error.ReactorNotRunning:
    # Returns quietly when stop an already stopped reactor.
    pass


# Twisted Protocol class can be inherited without __init__().
class ClientProtocol(Protocol):  # pylint: disable=W0232
  """Connects to shopfloor launcher, send a command, then print the result."""

  def connectionMade(self):
    """Passes command line arguments and current working directory to launcher.
    """
    json_cmd = {
      'args': self.factory.argv,
      'cwd': self.factory.cwd}
    # Launcher commands uses JSON line protocol, add trailing newline.
    self.transport.write(json.dumps(json_cmd, separators=(',', ':')) + '\n')

  def dataReceived(self, data):
    """Dumps received command output."""
    # The connection is controlled by remote peer. No need to call
    # StopReactor().
    print data


class CommandLineFactory(ClientFactory):
  """Twisted client factory that generates command line objects.

  Args:
    argv: sys.argv like argument list
    cwd: current working directory string
  """
  protocol = ClientProtocol

  def __init__(self, argv, cwd):
    self.argv = argv
    self.cwd = cwd

  def clientConnectionFailed(self, connector, reason):
    """Displays error message on client connection failed."""
    print 'ERROR: %s' % reason
    StopReactor()

  def clientConnectionLost(self, connector, reason):
    """Displays error message when connect lost unexpectly."""
    if not reason.check(error.ConnectionDone):
      print 'ERROR: %s' % reason
    StopReactor()


def CallLauncher():
  """Proxies command line arguments to launcher."""
  cmd = CommandLineFactory(sys.argv, os.getcwd())
  reactor.connectTCP('localhost', constants.COMMAND_PORT, cmd)
  reactor.run()


def GetShopfloordPid():
  """Calls ps to get shopfloord pid.

  Returns:
    Shopfloor daemon process ID. None when no running instance.
  """
  str_pid = SpawnOutput(['ps', '-C', 'shopfloord', '-o', 'pid=']).strip()
  if str_pid:
    # Returns only the first shopfloord found in ps -C output.
    return int(str_pid.split('\n')[0])
  return None


def GetChildProcesses(pid):
  """Recursively gets a flatten list of child process ID.

  Args:
    pid: the parent process ID.

  Returns:
    A list of child process ID in int. Empty list when no child process.
  """
  # Use 'ps --ppid' to get child pids.
  ps_output = SpawnOutput(['ps', '--ppid', str(pid), '-o', 'pid=']).strip()
  if not ps_output:
    return []
  child_pids = map(int, filter(None, ps_output.split('\n')))
  # And all grand child pids.
  grand_child_pids = []
  map((lambda p: grand_child_pids.extend(GetChildProcesses(p))), child_pids)
  return child_pids + grand_child_pids


def StopShopfloord():
  """Stops shopfloor daemon."""
  shopfloor_pid = GetShopfloordPid()
  stored_pid = shopfloor_pid
  if shopfloor_pid is None:
    return
  logging.info('Stopping shopfloor PID:%d', shopfloor_pid)
  waiting_pids = GetChildProcesses(shopfloor_pid)
  os.kill(shopfloor_pid, signal.SIGTERM)
  # Wait for shopfloord to shutdown and display its progress.
  while waiting_pids:
    logging.info('  Waiting processes: %s', waiting_pids)
    time.sleep(0.5)
    shopfloor_pid = GetShopfloordPid()
    if not shopfloor_pid:
      return
    if shopfloor_pid != stored_pid:
      # Found an extra shopfloord, send SIGTERM.
      stored_pid = shopfloor_pid
      os.kill(shopfloor_pid, signal.SIGTERM)
    waiting_pids = GetChildProcesses(shopfloor_pid)


def StartShopfloord(extra_args=None):
  """Starts shopfloor daemon with default YAML configuration.

  Shopfloor launcher loads YAML configuration that symlinked to a verified
  resource file.

  Args:
    extra_args: Extra arguments passed to shopfloord command line.
  """
  args = [os.path.join(env.runtime_dir, 'shopfloord')]
  if isinstance(extra_args, list):
    args.extend(extra_args)
  elif extra_args:
    logging.warning('Shopfloord extra_args should be a list.')
  log = open(os.path.join(env.runtime_dir, 'log', LOG_FILE), 'w')
  null = OpenDevNull()
  logging.info('Starting shopfloord...')
  pid = subprocess.Popen(args, stdin=null, stdout=log, stderr=log).pid
  with open(os.path.join(env.runtime_dir, 'run', PID_FILE), 'w') as f:
    f.write(str(pid))
  logging.info('Shopfloord started: PID=%d', pid)


@Command('deploy',
         CmdArg('-c', '--config',
                help='the YAML config file to deploy'))
def Deploy(args):
  """Deploys new shopfloor YAML configuration."""
  res_dir = env.GetResourcesDir()
  new_config_file = os.path.join(res_dir, args.config)
  if not os.path.isfile(new_config_file):
    logging.error('Config file not found: %s', new_config_file)
    return
  # Verify listed resources.
  try:
    resources = [os.path.join(res_dir, res) for res in
                 utils.ListResources(new_config_file)]
    map(utils.VerifyResource, resources)
  except (IOError, ShopFloorLauncherException) as err:
    logging.exception('Verify resources failed: %s', err)
    return
  # Get new factory.par resource name from YAML config.
  launcher_config = yamlconf.LauncherYAMLConfig(new_config_file)
  new_factory_par = os.path.join(
      res_dir, launcher_config['shopfloor']['factory_software'])
  # Restart shopfloor daemon.
  config_file = os.path.join(env.runtime_dir, CONFIG_FILE)
  factory_par = os.path.join(env.runtime_dir, FACTORY_SOFTWARE)
  prev_config_file = os.path.join(env.runtime_dir, PREV_CONFIG_FILE)
  prev_factory_par = os.path.join(env.runtime_dir, PREV_FACTORY_SOFTWARE)
  shopfloor_util = os.path.join(env.runtime_dir, SHOPFLOOR_UTIL)
  shopfloor_daemon = os.path.join(env.runtime_dir, SHOPFLOOR_DAEMON)
  StopShopfloord()
  try:
    file_utils.TryUnlink(prev_config_file)
    file_utils.TryUnlink(prev_factory_par)
    if os.path.isfile(config_file):
      shutil.move(config_file, prev_config_file)
    if os.path.isfile(factory_par):
      shutil.move(factory_par, prev_factory_par)
    os.symlink(new_factory_par, factory_par)
    os.symlink(new_config_file, config_file)
    if not os.path.isfile(shopfloor_util):
      os.symlink(factory_par, shopfloor_util)
    if not os.path.isfile(shopfloor_daemon):
      os.symlink(factory_par, shopfloor_daemon)
  except (OSError, IOError) as err:
    logging.exception('Can not deploy new config: %s (%s)',
                      new_config_file, err)
    logging.exception('Shopfloor didn\'t restart.')
    return
  StartShopfloord()


@Command('list')
def List(dummy_args):
  """Lists available configurations."""
  file_list = glob.glob(os.path.join(env.GetResourcesDir(), 'shopfloor.yaml#*'))
  config = None
  version = None
  note = None
  count = 0
  for fn in file_list:
    try:
      config = yaml.load(open(fn, 'r'))
      version = config['info']['version']
      note = config['info']['note']
    except:  # pylint: disable=W0702
      continue
    logging.info(os.path.basename(fn))
    logging.info('  - version: %s', version)
    logging.info('  - note:    %s', note)
    count += 1
  if count > 0:
    logging.info('OK: found %d configuration(s).', count)
  else:
    logging.info('ERROR: no configuration found.')


@Command('import',
         CmdArg('-b', '--bundle',
                help='import resources from bundle dir'),
         CmdArg('-f', '--file', nargs='+',
                help='import resources from file list'))
def Import(args):
  """Imports shopfloor resources."""
  if args.bundle:
    importer.BundleImporter(args.bundle).Import()
    return
  NotImplementedError('shopofloor import --file')


@Command('info')
def Info(dummy_args):
  """Calls launcher to display running configuration."""
  CallLauncher()


@Command('init')
def Init(dummy_args):
  """Initializes system folders with proper owner and group."""
  if not os.path.isdir(constants.SHOPFLOOR_INSTALL_DIR):
    print "Install folder not found!"
    print "Please create folder: \n\t%s\n" % constants.SHOPFLOOR_INSTALL_DIR
    print "And change the owner to current user ID."
    print "Example:"
    print "  for user 'sfuser' and group 'sf'"
    print "  sudo mkdir /var/db/factory"
    print "  sudo chown sfuser.sf /var/db/factory"
    sys.exit(-1)
  utils.CreateSystemFolders()


@Command('start')
def Start(dummy_args):
  """Starts shopfloor with default configuration."""
  StopShopfloord()
  StartShopfloord()


@Command('stop')
def Stop(dummy_args):
  """Stops running shopfloor instance."""
  StopShopfloord()


def main():
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  args = ParseCmdline('Shopfloor V2 command line utility.')
  args.command(args)

if __name__ == '__main__':
  main()
