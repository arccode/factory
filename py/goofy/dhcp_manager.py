#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import jsonrpclib
import logging
import os
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.utils import jsonrpc_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils


class DHCPManager(object):
  """The manager that provides DHCP service.

  Properties set from __init__ arguments:
    interface: The name of the network interface for DHCP.
    my_ip: The IP address for the DHCP server. The interface used will be
      set to this IP address.
    ip_start: The start of DHCP IP range.
    ip_end: The end of DHCP IP range.
    lease_time: How long in seconds before the DHCP lease expires.
    on_add: Optional callback function that's called when a client is issued
      a new IP address. The callback takes the IP address as the only argument.
    on_old: Similar to on_add, but called when a client is fed an IP address
      that's previously assigned to it.
    on_del: Similar to on_del, but called when a lease is revoked.
  """

  # Where callback files are placed
  CALLBACK_DIR = '/var/run/dhcpcd'

  # Callback file name prefix
  CALLBACK_PREFIX = 'dhcp_manager_cb_'

  def __init__(self, interface,
               my_ip='192.168.0.1',
               ip_start='192.168.0.10',
               ip_end='192.168.0.20',
               lease_time=3600,
               on_add=None,
               on_old=None,
               on_del=None):
    self._interface = interface
    self._my_ip = my_ip
    self._ip_start = ip_start
    self._ip_end = ip_end
    self._lease_time = lease_time
    self._rpc_server = None
    self._process = None
    self._dhcp_action = {'add': on_add, 'old': on_old, 'del': on_del}
    self._callback_port = None

  def StartDHCP(self):
    """Starts DHCP service."""
    self._callback_port = net_utils.FindUnusedTCPPort()
    self._rpc_server = jsonrpc_utils.JSONRPCServer(
        port=self._callback_port, methods={'Callback': self.DHCPCallback})
    self._rpc_server.Start()
    # __file__ may be a generated .pyc file that's not executable. Use .py.
    callback_file_target = __file__.replace('.pyc', '.py')
    callback_file_symlink = os.path.join(self.CALLBACK_DIR,
                                         '%s%d' % (self.CALLBACK_PREFIX,
                                                   self._callback_port))
    if not os.path.exists(self.CALLBACK_DIR):
      os.makedirs(self.CALLBACK_DIR)
    os.symlink(callback_file_target, callback_file_symlink)
    dhcp_range = '%s,%s,%d' % (self._ip_start, self._ip_end, self._lease_time)
    dns_port = net_utils.FindUnusedTCPPort()
    lease_file = '/var/lib/dhcpcd/dnsmasq-%s.leases' % self._interface
    # Make sure the interface is up
    net_utils.SetEthernetIp(self._my_ip, self._interface)
    # Start dnsmasq and have it call back to us on any DHCP event.
    self._process = process_utils.Spawn(
        ['dnsmasq', '--keep-in-foreground',
         '--dhcp-range', dhcp_range,
         '--interface', self._interface,
         '--bind-interfaces',
         '--port', str(dns_port),
         '--dhcp-leasefile=%s' % lease_file,
         '--dhcp-script', callback_file_symlink],
        sudo=True, log=True)
    # Make sure the IP address is set on the interface
    net_utils.SetEthernetIp(self._my_ip, self._interface)
    # Make sure DHCP packets are not blocked
    process_utils.Spawn(['iptables',
                         '--insert', 'INPUT',
                         '--protocol', 'udp',
                         '--dport', '67:68',
                         '--sport', '67:68',
                         '-j', 'ACCEPT'],
                        sudo=True)

  def StopDHCP(self):
    """Stops DHCP service."""
    self._process.terminate()
    self._process = None
    self._rpc_server.Destroy()
    self._rpc_server = None

  def DHCPCallback(self, argv):
    """RPC method that processes the parameters from dnsmasq.

    Based on the parameters, the appropriate callback action is invoked.

    Args:
      argv: The complete arguments received from dnsmasq callback.
    """
    if len(argv) < 4 or argv[1] not in self._dhcp_action:
      logging.error("Invalid DHCP callback: %s", argv)
      return
    action = self._dhcp_action[argv[1]]
    ip = argv[3]
    if action:
      action(ip)


if __name__ == '__main__':
  # Figure out what port to call back to
  filename = os.path.basename(sys.argv[0])
  if not filename.startswith(DHCPManager.CALLBACK_PREFIX):
    # Not callback. Do nothing.
    sys.exit(0)
  callback_port = int(filename[len(DHCPManager.CALLBACK_PREFIX):])

  # Forward whatever dnsmasq tells us to DHCPManager
  proxy = jsonrpclib.Server('http://127.0.0.1:%d' % callback_port,
                            transport=jsonrpc_utils.TimeoutJSONRPCTransport(1))
  proxy.Callback(sys.argv)
