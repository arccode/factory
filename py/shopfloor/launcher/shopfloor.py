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
import sys
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


def Stop():
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
    # The connection is controlled by remote peer. No need to call Stop().
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
    Stop()

  def clientConnectionLost(self, connector, reason):
    """Displays error message when connect lost unexpectly."""
    if not reason.check(error.ConnectionDone):
      print 'ERROR: %s' % reason
    Stop()


def CallLauncher():
  """Proxies command line arguments to launcher."""
  cmd = CommandLineFactory(sys.argv, os.getcwd())
  reactor.connectTCP('localhost', constants.COMMAND_PORT, cmd)
  reactor.run()

@Command('deploy')
def Deploy(dummy_args):
  """Calls launcher to deploy new configuration."""
  CallLauncher()


@Command('list')
def List(dummy_args):
  """Calls launcher to list available configurations."""
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
  raise NotImplementedError('shopfloor init')


def main():
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  args = ParseCmdline('Shopfloor V2 command line utility.')
  args.command(args)

if __name__ == '__main__':
  main()
