#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Simple TCP proxy.

This is a TCP proxy that designed for factory environment. Network layout
in factory are illustrated as following:
  [Remote Host] <---> [TCP Proxy] <---> DUT

In factory, unexpected exception might be happened at the portion involving
DUT. Those exceptions might cause remote host, using vendor's proprietary
software stack, into a strange state. To alleviate this behavior, we
introduce this proxy to keep the connection to remote host as stable as
possible and handle the DUT inside the proxy.

There are few cases on the DUT portion:
1) A DUT might leave the connection hanged
We are not able to detect at the time DUT disappeared, but will figure out
its status when the next time remote try to send bytes to DUTs.
The Protocol handler of old DUT will then unregistered itself and garbage
collected at the next boardcast.

2) DUT actively close the connection
The Protocol handler will unregistered itself immediately.

For the connection with remote host:
1) When a connection established
Factory instance will start to listen on local port and old Protocol will be
garbage collected.

2) When a connection lost
Protocol instance will mark itself as inactive and Factory instance will stop
accepting new connection from DUT. Retry with exponentially delays will start
after connection lost.
"""


import logging
import optparse
import pprint
import uuid

from twisted.internet.protocol import connectionDone
from twisted.internet.protocol import Factory
from twisted.internet.protocol import Protocol
from twisted.internet import reactor
from twisted.internet.protocol import ReconnectingClientFactory


class ClientProtocol(Protocol):

  def __init__(self):
    self.factory = None
    self.uuid = "ClientProtocol(%s)" % uuid.uuid4()

  def dataReceived(self, data):
    logging.info("%s: got %3d bytes from remote host", self.uuid, len(data))
    logging.debug("%s: got data %r from remote host", self.uuid, data)
    self.factory.boardcastData(data)

  def connectionMade(self):
    logging.info("%s: Connected to %s", self.uuid, self.transport.getPeer())

  def connectionLost(self, reason=connectionDone):
    del reason  # Unused.
    logging.info("%s: lost connection with remote", self.uuid)
    self.factory.active_client = None

  def __del__(self):
    logging.info("%s: __del__ is called()", self.uuid)


class ClientFactory(ReconnectingClientFactory):
  protocol = ClientProtocol

  def __init__(self, local_port):
    self.active_duts = {}      # Active to DUTs
    self.active_client = None  # Active protocol to remote
    self.listener = None
    self.local_port = local_port

  def boardcastData(self, data):
    logging.debug("boardcastData() is called, active clients:\n%s",
                  pprint.pformat(self.active_duts))
    for dut_uuid in list(self.active_duts.iterkeys()):
      # Clean inactive duts
      if self.active_duts[dut_uuid][1] is False:
        logging.debug(
            "Found %s marked itself as inactive, remove it.", dut_uuid)
        del self.active_duts[dut_uuid]
      else:
        logging.debug("Send %3d bytes to dut %s", len(data), dut_uuid)
        self.active_duts[dut_uuid][0].transport.write(data)

  def startedConnecting(self, connector):
    logging.info("Trying to connect to %r", connector.getDestination())

  def buildProtocol(self, addr):
    ret = ReconnectingClientFactory.buildProtocol(self, addr)
    logging.info("Connected. Reset delay")
    self.resetDelay()
    self.active_client = ret
    logging.info("Listening port %d", self.local_port)
    self.listener = reactor.listenTCP(self.local_port, ServerFactory(self))
    return ret

  def clientConnectionLost(self, connector, reason):
    ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
    logging.info(
        "Lost connection with remote (reason: %r), stop listening.", reason)
    self.active_client = None
    self.listener.stopListening()


class ServerProtocol(Protocol):

  def __init__(self, client_factory):
    self.client_factory = client_factory
    self.uuid = "ServerProtocol(%s)" % uuid.uuid4()
    logging.info("%s initialized and got ClientFactory %r",
                 self.uuid, self.client_factory)

  def dataReceived(self, data):
    logging.info("%s: got %3d bytes from remote dut", self.uuid, len(data))
    logging.debug("%s: got data %r from remote dut", self.uuid, data)
    if self.client_factory.active_client:
      self.client_factory.active_client.transport.write(data)
    else:
      logging.info(
          "%s found the other side is closed. unregistering self", self.uuid)
      self.transport.loseConnection()

  def connectionLost(self, reason=connectionDone):
    del reason  # Unused.
    logging.info(
        "%s: lost connection with dut %s", self.uuid, self.transport.getPeer())
    # Marked as closed in ClientFactory
    self.client_factory.active_duts[self.uuid] = (self, False)
    self.client_factory = None

  def connectionMade(self):
    logging.info("%s: accept %s", self.uuid, self.transport.getPeer())
    # Register to ClientFactory
    self.client_factory.active_duts[self.uuid] = (self, True)

  def __del__(self):
    logging.info("%s: __del__ is called()", self.uuid)


class ServerFactory(Factory):

  def __init__(self, client_factory):
    self.client_factory = client_factory
    self.uuid = "ServerFactory(%s)" % uuid.uuid4()
    logging.info(
        "%s initialized and got ClientFactory %r", self.uuid, client_factory)

  def buildProtocol(self, addr):
    del addr  # Unused.
    return ServerProtocol(self.client_factory)

  def __del__(self):
    logging.info("%s: __del__ is called()", self.uuid)


def main():
  parser = optparse.OptionParser()
  parser.add_option("--remote_host", dest="remote_host", type="string",
                    help="IP address of remote host.")
  parser.add_option("--remote_port", dest="remote_port", type="int",
                    help="Port number of remote host.")
  parser.add_option("--local_port", dest="local_port", type="int",
                    help="Local port number to listen.")
  parser.add_option("-v", "--verbose", dest="verbose", action="store_true",
                    help="Print detail logs.")

  (options, args) = parser.parse_args()
  if args:
    parser.error("Invalid args: %s" % " ".join(args))

  loggerLevel = logging.DEBUG if options.verbose else logging.INFO
  logging.basicConfig(level=loggerLevel, format="%(message)s")
  reactor.connectTCP(options.remote_host, options.remote_port,
                     ClientFactory(options.local_port), timeout=1)
  reactor.run()

if __name__ == "__main__":
  main()
