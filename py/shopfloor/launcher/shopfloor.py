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


import json
import os
import sys
from twisted.internet import error, reactor
from twisted.internet.protocol import Protocol, ClientFactory

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants


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
      'args': sys.argv,
      'cwd': os.getcwd()}
    self.transport.write(json.dumps(json_cmd, separators=(',', ':')) + '\n')

  def dataReceived(self, data):
    """Dumps received command output."""
    # The connection is controlled by remote peer. No need to call Stop().
    print data


# Twisted Factory class can be inherited without __init__().
class CommandLineFactory(ClientFactory):  # pylint: disable=W0232
  protocol = ClientProtocol

  def clientConnectionFailed(self, connector, reason):
    """Displays error message on client connection failed."""
    print 'ERROR: %s' % reason
    Stop()

  def clientConnectionLost(self, connector, reason):
    """Displays error message when connect lost unexpectly."""
    if not reason.check(error.ConnectionDone):
      print 'ERROR: %s' % reason
    Stop()


def main():
  cmd = CommandLineFactory()
  reactor.connectTCP('localhost', constants.COMMAND_PORT, cmd)
  reactor.run()

if __name__ == '__main__':
  main()
