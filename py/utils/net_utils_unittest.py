#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

from __future__ import print_function

import SimpleXMLRPCServer
import socket
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import net_utils


class TimeoutXMLRPCTest(unittest.TestCase):

  def __init__(self, *args, **kwargs):
    super(TimeoutXMLRPCTest, self).__init__(*args, **kwargs)
    self.client = None

  def setUp(self):
    self.port = net_utils.FindUnusedTCPPort()
    self.server = SimpleXMLRPCServer.SimpleXMLRPCServer(
        (net_utils.LOCALHOST, self.port),
        allow_none=True)
    self.server.register_function(time.sleep)
    self.thread = threading.Thread(target=self.server.serve_forever)
    self.thread.daemon = True
    self.thread.start()

  def tearDown(self):
    self.server.shutdown()

  def MakeProxy(self, timeout):
    return net_utils.TimeoutXMLRPCServerProxy(
        'http://%s:%d' % (net_utils.LOCALHOST, self.port),
        timeout=timeout, allow_none=True)

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

if __name__ == '__main__':
  unittest.main()
