#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

from __future__ import print_function

import SimpleXMLRPCServer
import socket
import threading
import time
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils


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

  def testIn(self):
    ip = net_utils.IP('192.168.1.50')
    cidr = net_utils.CIDR('192.168.0.0', 24)
    self.assertFalse(ip.IsIn(cidr))
    cidr = net_utils.CIDR('192.168.0.0', 16)
    self.assertTrue(ip.IsIn(cidr))


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
    self.assertEqual(network_cidr, net_utils.CIDR('10.0.2.0', 24))

    # Test 10.0.0.1/16 used out and another 10.0.1.1/24 subnet in use.
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.1.1', 24),
        ('10.0.0.1', 16)])
    self.assertEqual(network_cidr, net_utils.CIDR('10.1.0.0', 24))

    # Test 10.0.0.1/24 multiple
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(16, [
        ('10.0.0.1', 24),
        ('10.0.1.1', 24)])
    self.assertEqual(network_cidr, net_utils.CIDR('10.1.0.0', 16))

    # Test 10.0.0.1/8 used out
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.0.1', 8),
        ('172.16.0.1', 24)])
    self.assertEqual(network_cidr, net_utils.CIDR('172.16.1.0', 24))

    # Test 10.0.0.1/8, 172.16.0.0/12 used out
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(24, [
        ('10.0.0.1', 8),
        ('172.16.0.0', 12)])
    self.assertEqual(network_cidr, net_utils.CIDR('192.168.0.0', 24))

    # Test 192.168.0.0/16 172.168.0./12 used out, 192.168.0.0/22
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(22, [
        ('10.0.0.1', 22),
        ('10.0.4.1', 22)])
    self.assertEqual(network_cidr, net_utils.CIDR('10.0.8.0', 22))

    exclude_ip_list = [('10.0.0.1', 8), ('172.16.0.0', 12)]
    ip = int(net_utils.IP('192.168.0.0'))
    for prefix_bits in xrange(17, 31):
      exclude_ip_list.append((str(net_utils.IP(ip)), prefix_bits))
      ip += 2 ** (32 - prefix_bits)
    network_cidr = net_utils.GetUnusedIPV4RangeCIDR(16, exclude_ip_list)
    self.assertEqual(network_cidr, net_utils.CIDR('192.168.255.252', 30))

    exclude_ip_list = [('10.0.0.1', 8), ('172.16.0.0', 12)]
    ip = int(net_utils.IP('192.168.0.0'))
    for prefix_bits in xrange(17, 33):
      exclude_ip_list.append((str(net_utils.IP(ip)), prefix_bits))
      ip += 2 ** (32 - prefix_bits)
    with self.assertRaises(RuntimeError):
      network_cidr = net_utils.GetUnusedIPV4RangeCIDR(16, exclude_ip_list)

  def testGetNetworkInterfaceByPath(self):
    func_under_test = net_utils.GetNetworkInterfaceByPath
    interface_table = {
        '/sys/class/net/eth0': '/REAL_PATH/0/net/eth0',
        '/sys/class/net/eth1': '/REAL_PATH/1/net/eth1'}
    def MockRealPath(path):
      return interface_table.get(path, '')

    with mock.patch('glob.glob', return_value=interface_table.keys()):
      with mock.patch('os.path.realpath', side_effect=MockRealPath):
        self.assertEquals('eth0', func_under_test('eth0'))
        self.assertEquals('eth0', func_under_test('/REAL_PATH/0/net'))
        self.assertEquals('eth1', func_under_test('/REAL_PATH/1/net'))
        self.assertEquals(None, func_under_test('/WRONG_PATH'))

        self.assertIn(func_under_test('/REAL_PATH', True), ['eth0', 'eth1'])
        with self.assertRaises(ValueError):
          func_under_test('/REAL_PATH', False)

  def testGetDefaultGatewayInterface(self):
    # Successful case.
    mock_value = """\
    Kernel IP routing table
    Destination     Gateway         Genmask        Flags Metric Ref    Use Iface
    0.0.0.0         192.168.0.1     0.0.0.0        UG    600    0        0 wlan0
    """
    with mock.patch.object(process_utils, 'CheckOutput',
                           return_value=mock_value):
      ret = net_utils.GetDefaultGatewayInterface()
      self.assertEquals('wlan0', ret)

    # Duplicate case. It should return the first interface.
    mock_value = """\
    Kernel IP routing table
    Destination     Gateway         Genmask        Flags Metric Ref    Use Iface
    0.0.0.0         192.168.0.1     0.0.0.0        UG    600    0        0 wlan0
    0.0.0.0         192.168.1.1     0.0.0.0        UG    600    0        0 eth0
    """
    with mock.patch.object(process_utils, 'CheckOutput',
                           return_value=mock_value):
      ret = net_utils.GetDefaultGatewayInterface()
      self.assertEquals('wlan0', ret)

    # Empty case.
    mock_value = """\
    Kernel IP routing table
    Destination     Gateway         Genmask        Flags Metric Ref    Use Iface
    """
    with mock.patch.object(process_utils, 'CheckOutput',
                           return_value=mock_value):
      ret = net_utils.GetDefaultGatewayInterface()
      self.assertEquals(None, ret)

    # Failure case.
    mock_value = """Wrong content."""
    with mock.patch.object(process_utils, 'CheckOutput',
                           return_value=mock_value):
      with self.assertRaises(ValueError):
        ret = net_utils.GetDefaultGatewayInterface()


if __name__ == '__main__':
  unittest.main()
