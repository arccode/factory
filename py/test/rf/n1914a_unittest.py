#!/usr/bin/env python3
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for n1914a module.

If the IP of N1914A is omitted, it will start a local server to mock the
test equipment. All of the unittests assumed to simulate on port 1 if no
explicit annotation is given.
"""

import logging
import socketserver
import threading
import unittest

from cros.factory.test.rf.n1914a import N1914A
from cros.factory.utils import net_utils

NORMAL_ERR_RESPONSE = b'+0,"No error"\n'
NORMAL_ESR_REGISTER = b'+0\n'
NORMAL_OPC_RESPONSE = b'+1\n'


class MockTestServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
  allow_reuse_address = True


class MockServerHandler(socketserver.StreamRequestHandler):
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
  def AddCommandsLookup(cls, commands, wait=True):
    """Wrapper for adding commands."""
    if isinstance(commands, bytes):
      commands = [commands]

    cls.AddLookup(b'*CLS', None)
    for command in commands:
      cls.AddLookup(command, None)
      cls.AddLookup(b'SYST:ERR?', NORMAL_ERR_RESPONSE)
    if wait:
      cls.AddLookup(b'*OPC?', NORMAL_OPC_RESPONSE)

  @classmethod
  def AddQueryLookup(cls, command, response):
    """Wrapper for adding a success query."""
    cls.AddLookup(b'*CLS', None)
    cls.AddLookup(command, response + b'\n')
    cls.AddLookup(b'*ESR?', NORMAL_ESR_REGISTER)
    cls.AddLookup(b'SYST:ERR?', NORMAL_ERR_RESPONSE)

  @classmethod
  def ResetLookup(cls):
    cls.responses_lookup = []

  def __init__(self, *args, **kwargs):
    self.lookup = list(self.responses_lookup)
    socketserver.StreamRequestHandler.__init__(self, *args, **kwargs)

  def handle(self):
    while True:
      line = self.rfile.readline().rstrip(b'\n')
      if not line:
        break
      expected_input, output = self.lookup.pop(0)
      if line == expected_input:
        if output:
          self.wfile.write(output)
      else:
        raise ValueError('Expecting [%s] but got [%s]' % (
            expected_input, line))


class N1914ATest(unittest.TestCase):
  EXPECTED_MODEL = b'Agilent Technologies,N1914A,MY50001187,A2.01.06'
  HOST = net_utils.LOCALHOST

  # FETCH1_EXPECTED_RESPONSE is the IEEE 754 64 bit floating
  # point representation of FETCH1_EXPECTED_RESPONSE
  FETCH1_EXPECTED_RESPONSE = bytes(
      bytearray([192, 80, 67, 70, 215, 23, 57, 14]))
  FETCH1_EXPECTED_VALUE = -65.05119874255999

  def _AddInitialLookup(self):
    """Adds necessary lookup for every connection."""
    MockServerHandler.ResetLookup()
    MockServerHandler.AddLookup(b'*CLS', None)
    MockServerHandler.AddLookup(b'*IDN?', self.EXPECTED_MODEL + b'\n')
    MockServerHandler.AddLookup(b'*ESR?', NORMAL_ESR_REGISTER)
    MockServerHandler.AddLookup(b'SYST:ERR?', NORMAL_ERR_RESPONSE)

  def _StartMockServer(self):
    """Starts a thread for the mock equipment."""
    server_port = net_utils.FindUnusedTCPPort()
    mock_server = MockTestServer(
        (net_utils.LOCALHOST, server_port), MockServerHandler)
    # pylint: disable=no-member
    server_thread = threading.Thread(target=mock_server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    logging.info('Server loop running in thread %s with port %d',
                 server_thread.name, server_port)
    return (mock_server, server_port)

  def _StartTest(self):
    self.mock_server, self.server_port = self._StartMockServer()
    self.n1914a = N1914A(host=self.HOST, port=self.server_port, delay=0)

  def testSetAsciiFormat(self):
    QUERY = b'FORM?'
    EXPECTED_RESPONSE = b'ASC'
    MockServerHandler.AddCommandsLookup([b'FORM ASCii'])
    MockServerHandler.AddQueryLookup(QUERY, EXPECTED_RESPONSE)

    self._StartTest()
    self.n1914a.SetAsciiFormat()
    self.assertEqual(self.n1914a.Query(QUERY), EXPECTED_RESPONSE)

  def testSetRealFormat(self):
    QUERY = b'FORM?'
    EXPECTED_RESPONSE = b'REAL'
    MockServerHandler.AddCommandsLookup([b'FORM REAL'])
    MockServerHandler.AddQueryLookup(QUERY, EXPECTED_RESPONSE)

    self._StartTest()
    self.n1914a.SetRealFormat()
    self.assertEqual(self.n1914a.Query(QUERY), EXPECTED_RESPONSE)

  def testBasicConnect(self):
    self._StartTest()
    # Check the id.
    self.assertEqual(self.n1914a.id, self.EXPECTED_MODEL)

  def testToNormalMode(self):
    QUERY = b'SENSe1:MRATe?'
    EXPECTED_RESPONSE = b'NORM'
    MockServerHandler.AddCommandsLookup([b'SENSe1:MRATe NORMal'])
    MockServerHandler.AddQueryLookup(QUERY, EXPECTED_RESPONSE)

    self._StartTest()
    self.n1914a.ToNormalMode(port=1)
    self.assertEqual(self.n1914a.Query(QUERY), EXPECTED_RESPONSE)

  def testToDoubleMode(self):
    QUERY = b'SENSe1:MRATe?'
    EXPECTED_RESPONSE = b'DOUB'
    MockServerHandler.AddCommandsLookup([b'SENSe1:MRATe DOUBle'])
    MockServerHandler.AddQueryLookup(QUERY, EXPECTED_RESPONSE)

    self._StartTest()
    self.n1914a.ToDoubleMode(port=1)
    self.assertEqual(self.n1914a.Query(QUERY), EXPECTED_RESPONSE)

  def testToFastMode(self):
    QUERY = b'SENSe1:MRATe?'
    EXPECTED_RESPONSE = b'FAST'
    MockServerHandler.AddCommandsLookup([b'SENSe1:MRATe FAST'])
    MockServerHandler.AddQueryLookup(QUERY, EXPECTED_RESPONSE)

    self._StartTest()
    self.n1914a.ToFastMode(port=1)
    self.assertEqual(self.n1914a.Query(QUERY), EXPECTED_RESPONSE)

  def testSetRange(self):
    QUERY1 = b'SENSe1:POWer:AC:RANGe:AUTO?'
    EXPECTED_RESPONSE_ENABLE = b'1'
    EXPECTED_RESPONSE_DISABLE = b'0'
    QUERY2 = b'SENSe1:POWer:AC:RANGe?'
    EXPECTED_RESPONSE_2 = b'+0'

    MockServerHandler.AddCommandsLookup([b'SENSe1:POWer:AC:RANGe:AUTO 1'])
    MockServerHandler.AddQueryLookup(QUERY1, EXPECTED_RESPONSE_ENABLE)
    MockServerHandler.AddCommandsLookup(
        [b'SENSe1:POWer:AC:RANGe:AUTO 0', b'SENSe1:POWer:AC:RANGe 0'])
    MockServerHandler.AddQueryLookup(QUERY1, EXPECTED_RESPONSE_DISABLE)
    MockServerHandler.AddQueryLookup(QUERY2, EXPECTED_RESPONSE_2)

    self._StartTest()
    self.n1914a.SetRange(port=1, range_setting=None)
    self.assertEqual(self.n1914a.Query(QUERY1), EXPECTED_RESPONSE_ENABLE)

    self.n1914a.SetRange(port=1, range_setting=0)
    self.assertEqual(self.n1914a.Query(QUERY1), EXPECTED_RESPONSE_DISABLE)
    self.assertEqual(self.n1914a.Query(QUERY2), EXPECTED_RESPONSE_2)

    # TODO(itspeter): test if assertion will be trigger for invalid parameter.

  def testSetAverageFilter(self):
    QUERY1 = b'SENSe1:AVERage:STATe?'
    EXPECTED_RESPONSE_ENABLE = b'1'
    EXPECTED_RESPONSE_DISABLE = b'0'
    QUERY2 = b'SENSe1:AVERage:COUNt:AUTO?'
    QUERY3 = b'SENSe1:AVERage:COUNt?'
    EXPECTED_RESPONSE_3 = b'+100'

    MockServerHandler.AddCommandsLookup([b'SENSe1:AVERage:STATe 0'])
    MockServerHandler.AddQueryLookup(QUERY1, EXPECTED_RESPONSE_DISABLE)

    MockServerHandler.AddCommandsLookup([b'SENSe1:AVERage:STATe 1'])
    MockServerHandler.AddCommandsLookup(
        [b'SENSe1:AVERage:COUNt:AUTO 0', b'SENSe1:AVERage:COUNt 100'])

    MockServerHandler.AddQueryLookup(QUERY1, EXPECTED_RESPONSE_ENABLE)
    MockServerHandler.AddQueryLookup(QUERY2, EXPECTED_RESPONSE_DISABLE)
    MockServerHandler.AddQueryLookup(QUERY3, EXPECTED_RESPONSE_3)

    self._StartTest()
    self.n1914a.SetAverageFilter(port=1, avg_length=None)
    self.assertEqual(self.n1914a.Query(QUERY1), EXPECTED_RESPONSE_DISABLE)

    self.n1914a.SetAverageFilter(port=1, avg_length=100)
    self.assertEqual(self.n1914a.Query(QUERY1), EXPECTED_RESPONSE_ENABLE)
    self.assertEqual(self.n1914a.Query(QUERY2), EXPECTED_RESPONSE_DISABLE)
    self.assertEqual(self.n1914a.Query(QUERY3), EXPECTED_RESPONSE_3)

  def testMeasureOnceInBinary(self):
    MockServerHandler.AddLookup(b'FETCh1?',
                                self.FETCH1_EXPECTED_RESPONSE + b'\n')
    self._StartTest()
    power = self.n1914a.MeasureOnceInBinary(port=1)
    self.assertAlmostEqual(power, self.FETCH1_EXPECTED_VALUE)

  def testMeasureInBinary(self):
    MockServerHandler.AddLookup(b'FETCh1?',
                                self.FETCH1_EXPECTED_RESPONSE + b'\n')
    MockServerHandler.AddLookup(b'FETCh1?',
                                self.FETCH1_EXPECTED_RESPONSE + b'\n')
    self._StartTest()
    power = self.n1914a.MeasureInBinary(port=1, avg_length=2)
    self.assertAlmostEqual(power, self.FETCH1_EXPECTED_VALUE)

  def setUp(self):
    self._AddInitialLookup()
    self.mock_server = None
    self.server_port = None
    self.n1914a = None

  def tearDown(self):
    self.n1914a.Close()
    self.mock_server.shutdown()  # pylint: disable=no-member

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
