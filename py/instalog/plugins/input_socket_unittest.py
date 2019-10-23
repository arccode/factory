#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input socket plugin."""

from __future__ import print_function

import logging
import socket
import time
import unittest

import mock

import instalog_common  # pylint: disable=unused-import
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_sandbox
from instalog import testing
from instalog.utils import net_utils


class TestInputSocket(unittest.TestCase):

  def _CreatePlugin(self):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.FindUnusedPort()
    config = {
        'hostname': 'localhost',
        'port': self.port}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'input_socket', config=config, core_api=self.core)
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin  # pylint: disable=protected-access

  def _CreateSocket(self):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.connect((self.hostname, self.port))

  def _AssertSocketClosed(self):
    self.sock.settimeout(0.5)
    self.assertFalse(self.sock.recv(1))

  def _ConfirmTransaction(self):
    """Performs the confirm transaction handshake."""
    self.assertEqual('1', self.sock.recv(1))
    self.sock.sendall('1')
    self.assertEqual('1', self.sock.recv(1))

  def setUp(self):
    self._CreatePlugin()
    self._CreateSocket()

  def tearDown(self):
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())
    self.core.Close()

  def testInvalidHeader(self):
    self.sock.sendall('x\0')
    self._AssertSocketClosed()

  def testPingAndOneEvent(self):
    # Ping.
    self.sock.sendall('0\0')
    self.assertEqual('1', self.sock.recv(1))

    # One event.
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      '0\0')
    self._ConfirmTransaction()
    self._AssertSocketClosed()
    self.assertEqual(self.core.emit_calls, [[datatypes.Event({})]])

  @mock.patch('socket_common.SOCKET_TIMEOUT', 0.1)
  def testOutputTimeout(self):
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      '0\0')
    # Don't confirm the transaction.  Simulate network failure by shutting
    # down the socket.
    self.sock.shutdown(socket.SHUT_RDWR)
    self.sock.close()
    time.sleep(0.2)
    self.assertFalse(self.core.emit_calls)

  def testInvalidChecksum(self):
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '0000000000000000000000000000000000000000\0'
                      '0\0')
    self._AssertSocketClosed()
    self.assertEqual([], self.core.emit_calls)

  def testOneEventOneAttachment(self):
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      '1\0'
                      '13\0my_attachment'
                      '8c18ccf21585d969762e4da67bc890da8672ba5c\0'
                      '10\0XXXXXXXXXX'
                      '1c17e556736c4d23933f99d199e7c2c572895fd2\0')
    self._ConfirmTransaction()
    self._AssertSocketClosed()
    self.assertEqual(1, len(self.core.emit_calls))
    event_list = self.core.emit_calls[0]
    self.assertEqual(1, len(event_list))
    self.assertEqual({}, event_list[0].payload)
    self.assertEqual(1, len(event_list[0].attachments))
    self.assertEqual('my_attachment', list(event_list[0].attachments)[0])
    with open(next(iter(event_list[0].attachments.values()))) as f:
      self.assertEqual('XXXXXXXXXX', f.read())


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
