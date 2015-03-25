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


class IPTest(unittest.TestCase):
  def testInit(self):
    self.assertRaises(RuntimeError, net_utils.IP, 'invalid IP')
    assert net_utils.IP(0xc0a80000) == net_utils.IP('192.168.0.0')
    assert (net_utils.IP('2401:fa00:1:b:42a8:f0ff:fe3d:3ac1') ==
            net_utils.IP(0x2401fa000001000b42a8f0fffe3d3ac1, 6))


class CIDRTest(unittest.TestCase):
  def testSelectIP(self):
    cidr = net_utils.CIDR('192.168.0.0', 24)
    assert cidr.SelectIP(1) == net_utils.IP('192.168.0.1')
    assert cidr.SelectIP(2) == net_utils.IP('192.168.0.2')
    assert cidr.SelectIP(-3) == net_utils.IP('192.168.0.253')

  def testNetmask(self):
    cidr = net_utils.CIDR('192.168.0.0', 24)
    assert cidr.Netmask() == net_utils.IP('255.255.255.0')

    cidr = net_utils.CIDR('10.0.1.0', 22)
    assert cidr.Netmask() == net_utils.IP('255.255.252.0')


class UtilityFunctionTest(unittest.TestCase):
  def testGetUnusedIPRange(self):
    # Test 10.0.0.1/24 multiple
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.0.1', 24),
        ('10.0.1.1', 24)])
    assert network_cidr == net_utils.CIDR('10.0.2.0', 24)

    # Test 10.0.0.1/16 used out and another 10.0.1.1/24 subnet in use.
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.1.1', 24),
        ('10.0.0.1', 16)])
    assert network_cidr == net_utils.CIDR('10.1.0.0', 16)

    # Test 10.0.0.1/24 multiple
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(16, [
        ('10.0.0.1', 24),
        ('10.0.1.1', 24)])
    assert network_cidr == net_utils.CIDR('10.1.0.0', 16)

    # Test 10.0.0.1/8 used out
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.0.1', 8),
        ('172.16.0.1', 24)])
    assert network_cidr == net_utils.CIDR('172.16.1.0', 24)

    # Test 10.0.0.1/8, 172.16.0.0/12 used out
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.0.1', 8),
        ('172.16.0.0', 12)])
    assert network_cidr == net_utils.CIDR('192.168.0.0', 24)

    # Test 192.168.0.0/16 172.168.0./12 used out, 192.168.0.0/22
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(22, [
        ('10.0.0.1', 22),
        ('10.0.4.1', 22)])
    assert network_cidr == net_utils.CIDR('10.0.8.0', 22)


if __name__ == '__main__':
  unittest.main()
