#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input socket plugin."""

import logging
import socket
import threading
import time
import unittest
from unittest import mock

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.plugins import socket_common
from cros.factory.instalog import testing
from cros.factory.instalog.utils import net_utils


class TestInputPullSocket(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    config = {
        'hostname': 'localhost',
        'port': self.port}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'input_pull_socket', config=config, core_api=self.core)
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin  # pylint: disable=protected-access

  def _AcceptSocket(self, accept_sock):
    self.sock, _unused_addr = accept_sock.accept()
    accept_sock.shutdown(socket.SHUT_RDWR)
    accept_sock.close()

  def _AssertSocketClosed(self):
    self.sock.settimeout(0.5)
    self.assertFalse(self.sock.recv(1))

  def _ConfirmTransaction(self):
    """Performs the confirm transaction handshake."""
    self.assertEqual(b'1', self.sock.recv(1))
    self.sock.sendall(b'1')
    self.assertEqual(b'1', self.sock.recv(1))

  def setUp(self):
    self.sock = None
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()

    accept_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    accept_sock.bind((self.hostname, self.port))
    # Queue up to 1 requests.
    accept_sock.listen(1)

    t = threading.Thread(target=self._AcceptSocket, args=(accept_sock, ))
    t.start()
    self._CreatePlugin()
    t.join()

  def tearDown(self):
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()

  def testInvalidQong(self):
    # Qing.
    self.assertEqual(self.sock.recv(1), socket_common.QING)
    # Invalid qong.
    self.sock.sendall(b'*')
    self._AssertSocketClosed()

  def testInvalidPing(self):
    # Qing.
    self.assertEqual(self.sock.recv(1), socket_common.QING)
    # Qong.
    self.sock.sendall(socket_common.QING_RESPONSE)
    self.sock.sendall(b'x\0')
    self._AssertSocketClosed()

  def testQingPingAndOneEvent(self):
    # Qing.
    self.assertEqual(self.sock.recv(1), socket_common.QING)
    # Qong.
    self.sock.sendall(socket_common.QING_RESPONSE)
    # Ping.
    self.sock.sendall(b'0\0')
    self.assertEqual(b'1', self.sock.recv(1))

    # One event.
    self.sock.sendall(b'1\0'
                      b'8\0[{}, {}]'
                      b'50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      b'0\0')
    self._ConfirmTransaction()
    self._AssertSocketClosed()
    self.assertEqual(self.core.emit_calls, [[datatypes.Event({})]])

  @mock.patch('socket_common.SOCKET_TIMEOUT', 0.1)
  def testOutputTimeout(self):
    # Qing.
    self.assertEqual(self.sock.recv(1), socket_common.QING)
    # Qong.
    self.sock.sendall(socket_common.QING_RESPONSE)
    self.sock.sendall(b'1\0'
                      b'8\0[{}, {}]'
                      b'50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      b'0\0')
    # Don't confirm the transaction.  Simulate network failure by shutting
    # down the socket.
    self.sock.shutdown(socket.SHUT_RDWR)
    self.sock.close()
    time.sleep(0.2)
    self.assertFalse(self.core.emit_calls)

  def testInvalidChecksum(self):
    # Qing.
    self.assertEqual(self.sock.recv(1), socket_common.QING)
    # Qong.
    self.sock.sendall(socket_common.QING_RESPONSE)
    self.sock.sendall(b'1\0'
                      b'8\0[{}, {}]'
                      b'0000000000000000000000000000000000000000\0'
                      b'0\0')
    self._AssertSocketClosed()
    self.assertEqual([], self.core.emit_calls)

  def testOneEventOneAttachment(self):
    # Qing.
    self.assertEqual(self.sock.recv(1), socket_common.QING)
    # Qong.
    self.sock.sendall(socket_common.QING_RESPONSE)
    self.sock.sendall(b'1\0'
                      b'8\0[{}, {}]'
                      b'50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      b'1\0'
                      b'13\0my_attachment'
                      b'8c18ccf21585d969762e4da67bc890da8672ba5c\0'
                      b'10\0XXXXXXXXXX'
                      b'1c17e556736c4d23933f99d199e7c2c572895fd2\0')
    self._ConfirmTransaction()
    self._AssertSocketClosed()
    self.assertEqual(1, len(self.core.emit_calls))
    event_list = self.core.emit_calls[0]
    self.assertEqual(1, len(event_list))
    self.assertEqual({}, event_list[0].payload)
    self.assertEqual(1, len(event_list[0].attachments))
    self.assertEqual(b'my_attachment', list(event_list[0].attachments)[0])
    with open(next(iter(event_list[0].attachments.values()))) as f:
      self.assertEqual('XXXXXXXXXX', f.read())


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
