# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Advanced Networking-related utilities.

Utilities with more complex functionalities and required interaction with other
system components.
"""

import logging
import os
from multiprocessing import pool
import tempfile
import time

import dpkt
import netifaces
import pexpect

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.utils import FormatExceptionOnly
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils

try:
  import dbus
  HAS_DBUS = True
except ImportError:
  HAS_DBUS = False


INSERT_ETHERNET_DONGLE_TIMEOUT = 30


def GetAllIPs(iface_filter=None):
  """Returns all available IP addresses of all interfaces.

  Args:
    iface_filter: A filter to filter out unwanted network interfaces. It takes
                  the name of the interface and returns True for interfaces we
                  want and False for unwanted interfaces. Set this to None to
                  use all interfaces.

  Returns:
    A list of IP addresses.
  """
  ret = []
  if iface_filter is None:
    iface_filter = lambda x: True
  for iface in filter(iface_filter, netifaces.interfaces()):
    ifaddr = netifaces.ifaddresses(iface)
    if netifaces.AF_INET not in ifaddr:
      continue
    ret.extend([link['addr'] for link in ifaddr[netifaces.AF_INET]])
  return ret


def GetAllWiredIPs():
  """Returns all available IP addresses of all wired interfaces."""
  return GetAllIPs(lambda iface: iface.startswith('eth'))


def _SendDhclientCommand(arguments, interface,
                         timeout=5, expect_str=pexpect.EOF):
  """Calls dhclient as a foreground process with timeout.

  Because the read-only filesystem, using dhclient in ChromeOS needs a
  little tweaks on few paths.

  """
  DHCLIENT_SCRIPT = '/usr/local/sbin/dhclient-script'
  DHCLIENT_LEASE = os.path.join(factory.get_state_root(), 'dhclient.leases')
  assert timeout > 0, 'Must have a timeout'

  logging.info('Starting dhclient')
  dhcp_process = (
      pexpect.spawn(
          'dhclient',
          ['-sf', DHCLIENT_SCRIPT, '-lf', DHCLIENT_LEASE, '-d',
           '-v', '--no-pid', interface] + arguments, timeout))
  try:
    dhcp_process.expect(expect_str)
  except:
    logging.info('dhclient output before timeout - %r', dhcp_process.before)
    raise type_utils.Error(
        'Timeout when running DHCP command, check if cable is connected.')
  finally:
    dhcp_process.close()


def SendDhcpRequest(interface=None):
  """Sends dhcp request via dhclient.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, operation on a
    specific interface.
  """
  interface = interface or net_utils.FindUsableEthDevice(raise_exception=True)
  net_utils.Ifconfig(interface, True)
  _SendDhclientCommand([], interface,
                       expect_str=r'bound to (\d+\.\d+\.\d+\.\d+)')


def ReleaseDhcp(interface=None):
  """Releases a dhcp lease via dhclient.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, operation on a
    specific interface.
  """
  interface = interface or net_utils.FindUsableEthDevice(raise_exception=True)
  net_utils.Ifconfig(interface, True)
  _SendDhclientCommand(['-r'], interface)


def RenewDhcpLease(interface, timeout=3):
  """Renews DHCP lease on a network interface.

  Runs dhclient to obtain a new DHCP lease on the given network interface.

  Args:
    interface: The name of the network interface.
    timeout: Timeout for waiting DHCPOFFERS in seconds.

  Returns:
    True if a new lease is obtained; otherwise, False.
  """
  with file_utils.UnopenedTemporaryFile() as conf_file:
    with open(conf_file, "w") as f:
      f.write("timeout %d;" % timeout)
    p = process_utils.Spawn(['dhclient', '-1', '-cf', conf_file, interface])
    # Allow one second for dhclient to gracefully exit
    deadline = time.time() + timeout + 1
    while p.poll() is None:
      if time.time() > deadline:
        # Well, dhclient is ignoring the timeout value. Kill it.
        p.terminate()
        return False
      time.sleep(0.1)
  return p.returncode == 0


def PrepareNetwork(ip, force_new_ip=False, on_waiting=None):
  """High-level API to prepare networking.

  1. Wait for presence of ethernet connection (e.g., plug-in ethernet dongle).
  2. Setup IP.

  The operation may block for a long time. Do not run it in UI thread.

  Args:
    ip: The ip address to set. (Set to None if DHCP is used.)
    force_new_ip: Force to set new IP addr regardless of existing IP addr.
    on_waiting: Callback function, invoked when waiting for IP.
  """
  def _obtain_IP():
    if ip is None:
      SendDhcpRequest()
    else:
      net_utils.SetEthernetIp(ip, force=force_new_ip,
                              logger=factory.console.info)
    return True if net_utils.GetEthernetIp() else False

  factory.console.info('Detecting Ethernet device...')

  try:
    sync_utils.PollForCondition(
        poll_method=net_utils.FindUsableEthDevice,
        timeout_secs=INSERT_ETHERNET_DONGLE_TIMEOUT,
        condition_name='Detect Ethernet device')

    current_ip = net_utils.GetEthernetIp(net_utils.FindUsableEthDevice())
    if not current_ip or force_new_ip:
      if on_waiting:
        on_waiting()
      factory.console.info('Setting up IP address...')
      sync_utils.PollForCondition(poll_method=_obtain_IP,
                                  condition_name='Setup IP address')
  except:  # pylint: disable=W0702
    exception_string = FormatExceptionOnly()
    factory.console.error('Unable to setup network: %s', exception_string)
  factory.console.info('Network prepared. IP: %r', net_utils.GetEthernetIp())


def GetUnmanagedEthernetInterfaces():
  """Gets a list of unmanaged Ethernet interfaces.

  This method returns a list of network interfaces on which no DHCP server
  could be found.

  On CrOS devices, shill should take care of managing this, so we simply
  find Ethernet interfaces without IP addresses assigned. On non-CrOS devices,
  we try to renew DHCP lease with dhclient on each interface.

  Returns:
    A list of interface names.
  """
  def IsShillRunning():
    try:
      shill_status = process_utils.Spawn(['status', 'shill'], read_stdout=True,
                                         sudo=True)
      return (shill_status.returncode == 0 and
              'running' in shill_status.stdout_data)
    except OSError:
      return False

  def IsShillUsingDHCP(intf):
    if HAS_DBUS:
      bus = dbus.SystemBus()
      dev = bus.get_object("org.chromium.flimflam", "/device/%s" % intf)
      dev_intf = dbus.Interface(dev, "org.chromium.flimflam.Device")
      properties = dev_intf.GetProperties()
      for config in properties['IPConfigs']:
        if 'dhcp' in config:
          return True
      return False
    else:
      # We can't talk to shill without DBus, so let's just check for IP
      # address.
      return net_utils.GetEthernetIp(intf) is not None

  if IsShillRunning():
    # 'shill' running. Let's not mess with it. Just check whether shill got
    # DHCP response on each interface.
    return [intf for intf in net_utils.GetEthernetInterfaces() if
            not IsShillUsingDHCP(intf)]
  else:
    # 'shill' not running. Use dhclient.
    p = pool.ThreadPool(5)
    def CheckManaged(interface):
      if RenewDhcpLease(interface):
        return None
      else:
        return interface
    managed = p.map(CheckManaged, net_utils.GetEthernetInterfaces())
    return [x for x in managed if x]


def GetDHCPBootParameters(interface):
  """Get DHCP Bootp parameters from interface.

  Args:
    interface: the target interface managed by some DHCP server

  Returns:
    A tuple (ip, filename, hostname) if bootp parameter is found, else None.
  """
  dhcp_filter = '((port 67 or port 68) and (udp[8:1] = 0x2))'
  _, dump_file = tempfile.mkstemp()
  p = process_utils.Spawn("tcpdump -i %s -c 1 -w %s '%s'" %
                          (interface, dump_file, dhcp_filter), shell=True)

  # Send two renew requests to make sure tcmpdump can capture the response.
  for _ in range(2):
    if not RenewDhcpLease(interface):
      return RuntimeError('can not find DHCP server on %s' % interface)
    time.sleep(0.5)

  p.wait()

  with open(dump_file, 'r') as f:
    pcap = dpkt.pcap.Reader(f)
    for _, buf in pcap:
      eth = dpkt.ethernet.Ethernet(buf)
      udp = eth.ip.data
      dhcp = dpkt.dhcp.DHCP(udp.data)

      if dhcp['siaddr'] != 0 and len(dhcp['file'].strip('\x00')):
        ip = '.'.join([str(ord(x)) for x in
                       ('%x' % dhcp['siaddr']).decode('hex')])
        return (ip, dhcp['file'].strip('\x00'), dhcp['sname'].strip('\x00'))

  return None
