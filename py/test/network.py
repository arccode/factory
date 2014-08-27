# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Advanced Networking-related utilities."""

import os
import logging

import netifaces
import pexpect

import factory_common  # pylint: disable=W0611
from cros.factory import common
from cros.factory.test import factory
from cros.factory.test.utils import FormatExceptionOnly
from cros.factory.utils import net_utils


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
  DHCLIENT_SCRIPT = "/usr/local/sbin/dhclient-script"
  DHCLIENT_LEASE = os.path.join(factory.get_state_root(), "dhclient.leases")
  assert timeout > 0, 'Must have a timeout'

  logging.info('Starting dhclient')
  dhcp_process = pexpect.spawn('dhclient',
      ['-sf', DHCLIENT_SCRIPT, '-lf', DHCLIENT_LEASE,
       '-d', '-v', '--no-pid', interface] + arguments, timeout=timeout)
  try:
    dhcp_process.expect(expect_str)
  except:
    logging.info("dhclient output before timeout - %r", dhcp_process.before)
    raise common.Error(
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
                       expect_str=r"bound to (\d+\.\d+\.\d+\.\d+)")


def ReleaseDhcp(interface=None):
  """Releases a dhcp lease via dhclient.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, operation on a
    specific interface.
  """
  interface = interface or net_utils.FindUsableEthDevice(raise_exception=True)
  net_utils.Ifconfig(interface, True)
  _SendDhclientCommand(['-r'], interface)


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
    net_utils.PollForCondition(
        condition=lambda: True if net_utils.FindUsableEthDevice() else False,
        timeout=INSERT_ETHERNET_DONGLE_TIMEOUT,
        condition_name='Detect Ethernet device')

    current_ip = net_utils.GetEthernetIp(net_utils.FindUsableEthDevice())
    if not current_ip or force_new_ip:
      if on_waiting:
        on_waiting()
      factory.console.info('Setting up IP address...')
      net_utils.PollForCondition(condition=_obtain_IP,
                                 condition_name='Setup IP address')
  except:  # pylint: disable=W0702
    exception_string = FormatExceptionOnly()
    factory.console.error('Unable to setup network: %s', exception_string)
  factory.console.info('Network prepared. IP: %r', net_utils.GetEthernetIp())
