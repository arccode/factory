#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for input socket plugin."""

from __future__ import print_function

import logging
import socket
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_sandbox
from instalog import testing
from instalog.utils import net_utils


class TestInputSocket(unittest.TestCase):

  def _CreatePlugin(self, config={}):
    self.core = testing.MockCore()
    self.hostname = 'localhost'
    self.port = net_utils.GetUnusedPort()
    config = {
        'hostname': 'localhost',
        'port': self.port}
    self.sandbox = plugin_sandbox.PluginSandbox(
        'input_socket', config=config, core_api=self.core)
    self.sandbox.Start(True)
    self.plugin = self.sandbox._plugin

  def _CreateSocket(self):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.connect((self.hostname, self.port))

  def _AssertSocketClosed(self):
    self.sock.settimeout(0.5)
    self.assertFalse(self.sock.recv(1))

  def setUp(self):
    self._CreatePlugin()
    self._CreateSocket()

  def tearDown(self):
    self.sandbox.Stop(True)
    self.assertTrue(self.core.AllStreamsExpired())

  def testPing(self):
    self.sock.sendall('0\0')
    self.assertEquals('1', self.sock.recv(1))

  def testInvalidHeader(self):
    self.sock.sendall('x\0')
    self._AssertSocketClosed()

  def testOneEvent(self):
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      '0\0')
    self.assertEquals('1', self.sock.recv(1))
    self._AssertSocketClosed()
    # TODO(kitching): Remove when __nodeId__ is deprecated.
    self.core.emit_calls[0][0].payload.pop('__nodeId__', None)
    self.assertEquals(self.core.emit_calls, [[datatypes.Event({})]])

  def testInvalidChecksum(self):
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '0000000000000000000000000000000000000000\0'
                      '0\0')
    self._AssertSocketClosed()
    self.assertEquals([], self.core.emit_calls)

  def testOneEventOneAttachment(self):
    self.sock.sendall('1\0'
                      '8\0[{}, {}]'
                      '50005107138f95db8dfc3f44a84d607a5fc75669\0'
                      '1\0'
                      '13\0my_attachment'
                      '8c18ccf21585d969762e4da67bc890da8672ba5c\0'
                      '10\0XXXXXXXXXX'
                      '1c17e556736c4d23933f99d199e7c2c572895fd2\0')
    self.assertEquals('1', self.sock.recv(1))
    self._AssertSocketClosed()
    self.assertEqual(1, len(self.core.emit_calls))
    event_list = self.core.emit_calls[0]
    self.assertEqual(1, len(event_list))
    # TODO(kitching): Remove when __nodeId__ is deprecated.
    event_list[0].payload.pop('__nodeId__', None)
    self.assertEqual({}, event_list[0].payload)
    self.assertEqual(1, len(event_list[0].attachments))
    self.assertEqual('my_attachment', event_list[0].attachments.keys()[0])
    with open(event_list[0].attachments.values()[0]) as f:
      self.assertEqual('XXXXXXXXXX', f.read())


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG, format=log_utils.LOG_FORMAT)
  unittest.main()
