#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

import jsonrpclib
import SimpleXMLRPCServer
import socket
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import net_utils
from cros.factory.utils import test_utils
from cros.factory.common import TimeoutError


class TimeoutXMLRPCTest(unittest.TestCase):
  def __init__(self, *args, **kwargs):
    super(TimeoutXMLRPCTest, self).__init__(*args, **kwargs)
    self.client = None

  def setUp(self):
    self.port = test_utils.FindUnusedTCPPort()
    self.server = SimpleXMLRPCServer.SimpleXMLRPCServer(
      ('localhost', self.port),
      allow_none=True)
    self.server.register_function(time.sleep)
    self.thread = threading.Thread(target=self.server.serve_forever)
    self.thread.daemon = True
    self.thread.start()

  def tearDown(self):
    self.server.shutdown()

  def MakeProxy(self, timeout):
    return net_utils.TimeoutXMLRPCServerProxy(
      'http://localhost:%d' % self.port, timeout=timeout, allow_none=True)

  def runTest(self):
    self.client = self.MakeProxy(timeout=1)

    start = time.time()
    self.client.sleep(.001)  # No timeout
    delta = time.time() - start
    self.assertTrue(delta < 1, delta)

    start = time.time()
    try:
      self.client.sleep(2)  # Cause a timeout in 1 s
      self.fail('Expected exception')
    except socket.timeout:
      # Good!
      delta = time.time() - start
      self.assertTrue(delta > .25, delta)
      self.assertTrue(delta < 2, delta)

class JSONRPCTest(unittest.TestCase):
  def setUp(self):
    self.port = test_utils.FindUnusedTCPPort()
    self.server = net_utils.JSONRPCServer(
        port=self.port,
        methods={'Echo': self.echo,
                 'Sleep': self.sleep})
    self.simple_proxy = jsonrpclib.Server('http://localhost:%d' % self.port)
    self.timeout_proxy = jsonrpclib.Server(
        'http://localhost:%d' % self.port,
        transport=net_utils.TimeoutJSONRPCTransport(timeout=1))

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


class PollForConditionTest(unittest.TestCase):
  def _Counter(self, trigger=3):
    self.counter = self.counter + 1
    if self.counter > trigger:
      return True
    return False

  def setUp(self):
    self.counter = 1

  def testPollForCondition(self):
    self.assertEqual(True, net_utils.PollForCondition(
        condition=self._Counter, timeout=5))

  def testPollForConditionTimeout(self):
    self.assertRaises(TimeoutError, net_utils.PollForCondition,
        condition=lambda: self._Counter(trigger=30),
        timeout=2, poll_interval_secs=0.1)

if __name__ == '__main__':
  unittest.main()
