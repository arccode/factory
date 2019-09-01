#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import logging
import os
import random
import signal
import sys

import jsonrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.test.utils import network_utils
from cros.factory.utils import jsonrpc_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import service_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import sys_utils


class InterfaceProperty(object):
  """
  A data structure that stores configurations for an interface
  Properties
  """
  def __init__(self, name, cidr=None):
    assert isinstance(name, str)
    assert cidr is None or isinstance(cidr, net_utils.CIDR)

    self.name = name
    self.cidr = cidr


class DHCPManager(object):
  """The manager that provides DHCP service.

  Properties set from __init__ arguments:
    interfaces:
        A list of InterfaceProperty(s) to bind, or None to bind all available
        interfaces
    interface_blacklist:
        A list of interfaces (str) that shouldn't be managed, note that the
        default gateway interface is always excluded.
    bootp: A tuple (ip, filename, hostname) specifying the boot parameters.
    on_add: Optional callback function that's called when a client is issued a
        new IP address. The callback takes the IP address as the only argument.
    on_old: Similar to on_add, but called when a client is fed an IP address
        that's previously assigned to it.
    on_del: Similar to on_del, but called when a lease is revoked.
  """

  # Where run files are placed
  RUN_DIR = '/run/dhcp_manager'

  # Callback file name prefix
  CALLBACK_PREFIX = 'dhcp_manager_cb_'

  # Dnsmasq PID file name prefix
  PID_PREFIX = 'dnsmasq_dhcp_manager_pid_'

  # Lease file name prefix
  LEASE_PREFIX = 'dnsmasq_leases_'

  def __init__(self,
               interfaces=None,
               interface_blacklist=None,
               exclude_ip_prefix=None,
               lease_time=3600,
               bootp=None,
               on_add=None,
               on_old=None,
               on_del=None):
    self._interfaces = interfaces
    self._interface_blacklist = interface_blacklist or []
    self._exclude_ip_prefix = exclude_ip_prefix or []
    self._lease_time = lease_time
    self._bootp = bootp
    self._rpc_server = None
    self._process = None
    self._dhcp_action = {'add': on_add, 'old': on_old, 'del': on_del}
    self._callback_port = None
    self._handled_interfaces = []

  def _GetAvailibleInterfaces(self):
    return [InterfaceProperty(interface)
            for interface in network_utils.GetUnmanagedEthernetInterfaces()
            if interface not in self._interface_blacklist]

  def _CollectInterfaceAndIPRange(self):
    interfaces = self._interfaces or self._GetAvailibleInterfaces()
    dhcp_ranges = []

    used_range = list(self._exclude_ip_prefix or [])  # make a copy

    for interface in interfaces:
      ip_mask = net_utils.GetEthernetIp(interface.name, netmask=True)
      (ip, prefix) = ip_mask  # pylint: disable=unpacking-non-sequence
      cidr = None
      if ip and prefix:
        cidr = net_utils.CIDR(ip, prefix)
        logging.info('IFACE %s already assigned to %s',
                     interface.name, cidr)
        if int(cidr.IP) & ~int(cidr.Netmask()) != 1:
          logging.warn('However, the host part is not 1, will assign new IP.')
          cidr = None
      if not cidr:
        cidr = net_utils.GetUnusedIPV4RangeCIDR(exclude_ip_prefix=used_range,
                                                exclude_local_interface_ip=True)
        logging.info('DHCPManager: IFACE: %s will be assigned to %s',
                     interface.name, cidr)
      # Make sure the interface is up
      net_utils.SetEthernetIp(str(cidr.SelectIP(1)), interface.name,
                              str(cidr.Netmask()), force=True)

      used_range.append((str(cidr.SelectIP(1)), cidr.prefix))
      ip_start = cidr.SelectIP(2)
      ip_end = cidr.SelectIP(-3)
      dhcp_ranges.extend(['--dhcp-range',
                          '%s,%s,%d' % (ip_start, ip_end, self._lease_time)])
    interfaces = [interface.name for interface in interfaces]
    return interfaces, dhcp_ranges

  def GetHandledInterfaces(self):
    return self._handled_interfaces

  def StartDHCP(self):
    """Starts DHCP service."""
    if not os.path.exists(self.RUN_DIR):
      os.makedirs(self.RUN_DIR)
    self._callback_port = net_utils.FindUnusedTCPPort()
    self._rpc_server = jsonrpc_utils.JSONRPCServer(
        port=self._callback_port, methods={'Callback': self.DHCPCallback})
    self._rpc_server.Start()
    # __file__ may be a generated .pyc file that's not executable. Use .py.
    callback_file_target = __file__.replace('.pyc', '.py')
    callback_file_symlink = os.path.join(self.RUN_DIR,
                                         '%s%d' % (self.CALLBACK_PREFIX,
                                                   self._callback_port))
    os.symlink(callback_file_target, callback_file_symlink)

    interfaces, dhcp_ranges = self._CollectInterfaceAndIPRange()
    self._handled_interfaces = interfaces

    dns_port = net_utils.FindUnusedTCPPort()
    uid = random.getrandbits(64)
    lease_file = os.path.join(self.RUN_DIR,
                              '%s%016x' % (self.LEASE_PREFIX, uid))
    pid_file = os.path.join(self.RUN_DIR,
                            '%s%016x' % (self.PID_PREFIX, uid))
    # Start dnsmasq and have it call back to us on any DHCP event.

    cmd = ['dnsmasq',
           '--no-daemon',
           '--port', str(dns_port),
           '--no-dhcp-interface=%s' % net_utils.GetDefaultGatewayInterface(),
           '--dhcp-leasefile=%s' % lease_file,
           '--pid-file=%s' % pid_file,
           '--dhcp-script', callback_file_symlink]
    cmd += ['--interface=%s' % ','.join(interfaces)]
    cmd += dhcp_ranges
    if self._bootp:
      cmd.append('--dhcp-boot=%s,%s,%s' %
                 (self._bootp[1], self._bootp[2], self._bootp[0]))
    self._process = process_utils.Spawn(cmd, sudo=True, log=True)
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
    for interface in self._handled_interfaces:
      net_utils.Ifconfig(interface, enable=False)
    callback_file_symlink = os.path.join(self.RUN_DIR,
                                         '%s%d' % (self.CALLBACK_PREFIX,
                                                   self._callback_port))
    os.unlink(callback_file_symlink)

  def DHCPCallback(self, argv):
    """RPC method that processes the parameters from dnsmasq.

    Based on the parameters, the appropriate callback action is invoked.

    Args:
      argv: The complete arguments received from dnsmasq callback.
      argv[1]: The action, which is a string containing, "add", "old" or "del".
      argv[2]: The dongle mac address of connected DUT.
      argv[3]: The ip address of connected DUT.
    """
    if len(argv) < 4 or argv[1] not in self._dhcp_action:
      logging.error("Invalid DHCP callback: %s", argv)
      return
    action = self._dhcp_action[argv[1]]
    dongle_mac_address = argv[2]
    ip = argv[3]
    if action:
      action(ip, dongle_mac_address)

  @classmethod
  def CleanupStaleInstance(cls):
    """Kills all running dnsmasq instance and clean up run directory."""
    if not os.path.exists(cls.RUN_DIR):
      return
    for run_file in os.listdir(cls.RUN_DIR):
      if run_file.startswith(cls.PID_PREFIX):
        intf = run_file[len(cls.PID_PREFIX):]
        full_run_path = os.path.join(cls.RUN_DIR, run_file)
        with open(full_run_path, 'r') as f:
          pid = int(f.read())
        try:
          os.kill(pid, signal.SIGKILL)
        except OSError:
          pass
        net_utils.Ifconfig(intf, enable=False)
        os.unlink(full_run_path)
      if run_file.startswith(cls.CALLBACK_PREFIX):
        os.unlink(os.path.join(cls.RUN_DIR, run_file))


def StartDHCPManager(interfaces=None,
                     blacklist_file=None,
                     exclude_ip_prefix=None,
                     lease_time=None,
                     on_add=None,
                     on_old=None,
                     on_del=None,
                     bootp_from_default_gateway=False):

  DHCPManager.CleanupStaleInstance()
  if sys_utils.InCrOSDevice():
    # Wait for shill to start
    sync_utils.WaitFor(lambda: service_utils.GetServiceStatus('shill') ==
                       service_utils.Status.START, 15)

  bootp_params = None
  if bootp_from_default_gateway:
    # Get bootp parameters from gateway DHCP server
    default_iface = sync_utils.WaitFor(net_utils.GetDefaultGatewayInterface, 10)
    bootp_params = network_utils.GetDHCPBootParameters(default_iface)

  # arguments for DHCP manager
  kargs = {
      'interfaces': interfaces,
      'interface_blacklist': network_utils.GetDHCPInterfaceBlacklist(
          blacklist_file),
      'exclude_ip_prefix': exclude_ip_prefix,
      'lease_time': lease_time,
      'bootp': bootp_params,
      'on_add': on_add,
      'on_old': on_old,
      'on_del': on_del}

  # remove None to use default value
  kargs = {k: v for (k, v) in kargs.iteritems() if v is not None}

  manager = DHCPManager(**kargs)
  manager.StartDHCP()

  # Start NAT service
  interfaces = manager.GetHandledInterfaces()
  managed_interfaces = [x for x in net_utils.GetEthernetInterfaces()
                        if x not in interfaces]
  if not managed_interfaces:
    return manager
  nat_out_interface = managed_interfaces[0]
  net_utils.StartNATService(interfaces, nat_out_interface)

  return manager


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
