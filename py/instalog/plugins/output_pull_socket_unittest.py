#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for output socket plugin."""

import logging
import tempfile
import time
import unittest
from unittest import mock

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.plugins import output_socket
from cros.factory.instalog.plugins import socket_common
from cros.factory.instalog import testing


# pylint: disable=protected-access
class TestOutputPullSocket(unittest.TestCase):

  def setUp(self):
    self.core = testing.MockCore()
    config = {
        'hostname': 'localhost',
        'port': 8000,  # Does not actually need a valid available port.
        'timeout': 1}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'output_pull_socket', config=config, core_api=self.core)

    # Mock out the socket, accept socket and set up default EventStream.
    self.sock = mock.MagicMock()
    self.sock.recv.return_value = '1'  # Always return success.
    self.sock.recvfrom.return_value = socket_common.QING, ('add0', 1)

    accept_sock = mock.MagicMock()
    self.patcher = mock.patch('socket.socket', return_value=accept_sock)
    self.patcher.start()
    accept_sock.accept.return_value = self.sock, ('add0', 1)

    self.stream = self.core.GetStream(0)  # Only need one BufferEventStream.

    # Start the plugin.
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin

  def tearDown(self):
    self.sandbox.Stop(True)
    self.patcher.stop()
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()

  def _GetSentData(self):
    data = b''.join([x[1][0] for x in self.sock.sendall.mock_calls])
    self.sock.sendall.mock_calls = []
    return data

  def testQing(self):
    self.assertTrue(self.plugin.GetSocket())
    self.assertEqual(self._GetSentData(), socket_common.QING_RESPONSE)  # Qong.

  def testInvalidQing(self):
    self.sock.recvfrom.return_value = '*'
    self.assertFalse(self.plugin.GetSocket())

  def testPing(self):
    self.assertTrue(self.plugin.GetSocket())
    self.assertEqual(self._GetSentData(), socket_common.QING_RESPONSE)  # Qong.
    sender = output_socket.OutputSocketSender(
        self.plugin.logger.name, self.plugin._sock, self.plugin)
    sender.Ping()
    time.sleep(1)
    self.assertEqual(
        b'0\0',  # ping
        self._GetSentData())

  def testMidTransmissionFailure(self):
    with mock.patch.object(
        output_socket.OutputSocketSender, 'Ping', return_value=True):
      with mock.patch.object(self.sock, 'sendall', side_effect=Exception):
        self.stream.Queue([datatypes.Event({})])
        self.sandbox.Flush(0.1, True)
        self.assertFalse(self.stream.Empty())

  def testInvalidPong(self):
    self.assertTrue(self.plugin.GetSocket())
    self.assertEqual(self._GetSentData(), socket_common.QING_RESPONSE)  # Qong.
    sender = output_socket.OutputSocketSender(
        self.plugin.logger.name, self.plugin._sock, self.plugin)
    self.sock.recv.return_value = 'x'
    self.assertFalse(sender.Ping())

  def testOneEvent(self):
    event = datatypes.Event({})
    with mock.patch.object(datatypes.Event, 'Serialize', return_value='EVENT'):
      self.stream.Queue([event])
      self.sandbox.Flush(2, True)
      self.assertEqual(socket_common.QING_RESPONSE +  # qong
                       b'0\0'  # ping
                       b'1\0'
                       b'5\0'
                       b'EVENT'
                       b'7c90977a1d83c431f761e4bae201bddd4a6f31d6\0'
                       b'0\0'
                       b'1',  # confirmation
                       self._GetSentData())
    self.assertTrue(self.stream.Empty())

  def testOneEventOneAttachment(self):
    with tempfile.NamedTemporaryFile('w') as f:
      f.write('XXXXXXXXXX')
      f.flush()
      event = datatypes.Event({}, {'my_attachment': f.name})
      with mock.patch.object(datatypes.Event, 'Serialize',
                             return_value='EVENT'):
        self.stream.Queue([event])
        self.sandbox.Flush(2, True)
        self.assertEqual(socket_common.QING_RESPONSE +  # qong
                         b'0\0'  # ping
                         b'1\0'
                         b'5\0'
                         b'EVENT'
                         b'7c90977a1d83c431f761e4bae201bddd4a6f31d6\0'
                         b'1\0'
                         b'13\0my_attachment'
                         b'8c18ccf21585d969762e4da67bc890da8672ba5c\0'
                         b'10\0XXXXXXXXXX'
                         b'1c17e556736c4d23933f99d199e7c2c572895fd2\0'
                         b'1',  # confirmation
                         self._GetSentData())
    self.assertTrue(self.stream.Empty())


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
