#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSONRPC-related utilities."""

from __future__ import print_function

import jsonrpclib
import socket
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import jsonrpc_utils
from cros.factory.utils import net_utils
from cros.factory.utils import test_utils


class JSONRPCTest(unittest.TestCase):
  def setUp(self):
    self.port = test_utils.FindUnusedTCPPort()
    self.server = jsonrpc_utils.JSONRPCServer(
        port=self.port,
        methods={'Echo': self.echo,
                 'Sleep': self.sleep})
    self.simple_proxy = jsonrpclib.Server(
        'http://%s:%d' % (net_utils.LOCALHOST, self.port))
    self.timeout_proxy = jsonrpclib.Server(
        'http://%s:%d' % (net_utils.LOCALHOST, self.port),
        transport=jsonrpc_utils.TimeoutJSONRPCTransport(timeout=1))

  def tearDown(self):
    self.server.Destroy()

  def echo(self, s):
    return s

  def sleep(self, t):
    time.sleep(t)

  def testServer(self):
    self.server.Start()
    time.sleep(0.1) # Wait for the server to start
    self.assertTrue(self.simple_proxy.IsAlive())
    self.assertEqual(self.simple_proxy.Echo('test'), 'test')

    # Check the UUID remains the same for the same server instance
    self.assertEqual(self.simple_proxy.GetUuid(), self.simple_proxy.GetUuid())

  def testTimeoutProxy(self):
    self.server.Start()

    start = time.time()
    self.timeout_proxy.Sleep(.001) # No timeout
    delta = time.time() - start
    self.assertTrue(delta < 1, delta)

    start = time.time()
    try:
      self.timeout_proxy.Sleep(2) # Cause a timeout in 1 s
      self.fail('Expected exception')
    except socket.timeout:
      delta = time.time() - start
      self.assertTrue(delta > .25, delta)
      self.assertTrue(delta < 2, delta)

    # Check the server is still alive
    self.assertEqual('alive', self.simple_proxy.Echo('alive'))

if __name__ == '__main__':
  unittest.main()
