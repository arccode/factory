#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for lan_scpi module.

It starts a local server to mock the test equipment.
"""

from __future__ import print_function

import logging
import SocketServer
import threading
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rf import lan_scpi
from cros.factory.utils import net_utils
from cros.factory.utils import type_utils


class MockTestServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
  allow_reuse_address = True


class MockServerHandler(SocketServer.StreamRequestHandler):
  """A mocking handler for socket.

  This handler responses client based on its pre-defined lookup table.
  Lookup table can be config with AddLookup() and ResetLookup().

  Exceptions will be raised if recieves unexpected message from client.
  """
  responses_lookup = []

  @classmethod
  def AddLookup(cls, input_line, response):
    cls.responses_lookup.append((input_line, response))

  @classmethod
  def ResetLookup(cls):
    cls.responses_lookup = []

  def __init__(self, *args, **kwargs):
    self.lookup = list(self.responses_lookup)
    SocketServer.StreamRequestHandler.__init__(self, *args, **kwargs)

  def handle(self):
    while True:
      line = self.rfile.readline().rstrip('\n')
      if not line:
        break
      expected_input, output = self.lookup.pop(0)
      if line == expected_input:
        if output:
          self.wfile.write(output)
      else:
        raise ValueError('Expecting [%s] but got [%s]' % (
            expected_input, line))


class LanScpiTest(unittest.TestCase):
  EXPECTED_MODEL = 'Agilent Technologies,N1914A,MY50001187,A2.01.06'
  NORMAL_ERR_RESPONSE = '+0,"No error"\n'
  NORMAL_ESR_REGISTER = '+0\n'
  NORMAL_OPC_RESPONSE = '+1\n'

  def _AddInitialLookup(self):
    """Adds necessary lookup for every connection."""
    MockServerHandler.ResetLookup()
    MockServerHandler.AddLookup('*CLS', None)
    MockServerHandler.AddLookup('*IDN?', self.EXPECTED_MODEL + '\n')
    MockServerHandler.AddLookup('*ESR?', self.NORMAL_ESR_REGISTER)
    MockServerHandler.AddLookup('SYST:ERR?', self.NORMAL_ERR_RESPONSE)

  def _StartMockServer(self):
    """Starts a thread for the mock equipment."""
    server_port = net_utils.FindUnusedTCPPort()
    mock_server = MockTestServer(
        (net_utils.LOCALHOST, server_port), MockServerHandler)
    server_thread = threading.Thread(target=mock_server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    logging.info('Server loop running in thread %s with port %d',
                 server_thread.name, server_port)
    return (mock_server, server_port)

  def _StartTest(self):
    self.mock_server, self.server_port = self._StartMockServer()
    self.lan_scpi = lan_scpi.LANSCPI(
        host=net_utils.LOCALHOST, port=self.server_port, timeout=1, delay=0,
        in_main_thread=True)

  def testBasicConnect(self):
    self._StartTest()
    # Check the id.
    self.assertEqual(self.lan_scpi.id, self.EXPECTED_MODEL)

  def testSend(self):
    # Setup the mock equipment.
    TEST_COMMAND = 'SENSe1:AVERage:STATE 0'
    MockServerHandler.AddLookup('*CLS', None)
    MockServerHandler.AddLookup(TEST_COMMAND, None)
    MockServerHandler.AddLookup('SYST:ERR?', self.NORMAL_ERR_RESPONSE)
    MockServerHandler.AddLookup('*OPC?', self.NORMAL_OPC_RESPONSE)

    self._StartTest()
    self.lan_scpi.Send(TEST_COMMAND)

  def testSendWrongCommand(self):
    TEST_COMMAND = 'CC'
    UNKNOWN_COMMAND_RESPONSE = '-113,"Undefined header;CC<Err>$<NL>"\n'
    MockServerHandler.AddLookup('*CLS', None)
    MockServerHandler.AddLookup(TEST_COMMAND, None)
    MockServerHandler.AddLookup('SYST:ERR?', UNKNOWN_COMMAND_RESPONSE)
    MockServerHandler.AddLookup('*OPC?', self.NORMAL_OPC_RESPONSE)

    self._StartTest()
    self.assertRaisesRegexp(lan_scpi.Error, 'Undefined header',
                            self.lan_scpi.Send, TEST_COMMAND)

  def testQuery(self):
    TEST_COMMAND = 'FETCh?'
    MockServerHandler.AddLookup('*CLS', None)
    MockServerHandler.AddLookup(TEST_COMMAND, '33333\n')
    MockServerHandler.AddLookup('*ESR?', self.NORMAL_ESR_REGISTER)
    MockServerHandler.AddLookup('SYST:ERR?', self.NORMAL_ERR_RESPONSE)

    self._StartTest()
    self.lan_scpi.Query(TEST_COMMAND)

  def testQueryTimeout(self):
    # Setup the mock equipment.
    TEST_COMMAND = 'FETCh?'
    self._AddInitialLookup()
    MockServerHandler.AddLookup('*CLS', None)
    # Intensionally mute the output to trigger timeout
    MockServerHandler.AddLookup(TEST_COMMAND, '3333')
    MockServerHandler.AddLookup('*ESR?', None)
    MockServerHandler.AddLookup('SYST:ERR?', None)

    self._StartTest()
    self.assertRaisesRegexp(type_utils.TimeoutError, 'Timeout',
                            self.lan_scpi.Query, TEST_COMMAND)

  def setUp(self):
    self._AddInitialLookup()
    self.mock_server = None
    self.server_port = None
    self.lan_scpi = None

  def tearDown(self):
    self.lan_scpi.Close()
    self.mock_server.shutdown()

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
