# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

import glob
import httplib
import logging
import os
import pexpect
import re
import subprocess
import time
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.common import Error, TimeoutError
from cros.factory.test import factory
from cros.factory.test.utils import FormatExceptionOnly
from cros.factory.utils.process_utils import Spawn, SpawnOutput

DEFAULT_TIMEOUT = 10
INSERT_ETHERNET_DONGLE_TIMEOUT = 30

def Ifconfig(devname, enable, sleep_time_secs=1):
  """Brings up/down interface.

  Args:
    devname: Device name.
    enable: True is to bring up interface. False is down.
    sleep_time_secs: The sleeping time after ifconfig up.
  """
  Spawn(['ifconfig', devname, 'up' if enable else 'down'],
      check_call=True, log=True)
  # Wait for device to settle down.
  time.sleep(sleep_time_secs)

class TimeoutXMLRPCTransport(xmlrpclib.Transport):
  """Transport subclass supporting timeout."""
  def __init__(self, timeout=DEFAULT_TIMEOUT, *args, **kwargs):
    xmlrpclib.Transport.__init__(self, *args, **kwargs)
    self.timeout = timeout

  def make_connection(self, host):
    conn = httplib.HTTPConnection(host, timeout=self.timeout)
    return conn

class TimeoutXMLRPCServerProxy(xmlrpclib.ServerProxy):
  """XML/RPC ServerProxy supporting timeout."""
  def __init__(self, uri, timeout=10, *args, **kwargs):
    if timeout:
      kwargs['transport'] = TimeoutXMLRPCTransport(
        timeout=timeout)
    xmlrpclib.ServerProxy.__init__(self, uri, *args, **kwargs)

def FindUsableEthDevice(raise_exception=False):
  """Find the real ethernet interface when the flimflam is unavailable.

  Some devices with 4G modules may bring up fake eth interfaces during
  the factory flow. Flimflam is often used to tell the real interface type
  in the case. Unfortunately, we may sometimes need to turn it off to
  perform tests on network components. We thus need another way to reliably
  distinguish the real interface type.

  Args:
    raise_exception: True to raise exception when no interface available.
  """
  good_eth = None
  last_level = 0
  candidates = glob.glob('/sys/class/net/eth*')
  for path in candidates:
    dev = os.path.basename(path)
    p = subprocess.Popen('ethtool %s' % dev, shell=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stat = p.communicate()[0]

    # A 4G introduced ethernet interface would not be able to report its
    # setting data because it won't get online during the factory flow.
    # In case that there are several real ethernet interfaces available,
    # we favor the one that has the cable connected end-to-end.
    current_level = 0
    if 'Supported ports:' in stat:
      current_level = 1
      if 'Link detected: yes' in stat:
        current_level = 2
    if current_level > last_level:
      good_eth = dev
      last_level = current_level
  if raise_exception and not good_eth:
    raise Error('No Ethernet interface available')
  return good_eth

def SetEthernetIp(ip, interface=None, force=False):
  """Sets the IP address for Ethernet.

  Args:
    ip: The ip address want to set.
    interface: The target interface. The interface will be automatically
        assigned by Connection Manager if None is given.
    force: If force is False, the address is set only if the interface
        does not already have an assigned IP address.
  """
  interface = interface or FindUsableEthDevice(raise_exception=True)
  Ifconfig(interface, True)
  current_ip = GetEthernetIp(interface)
  if force or not current_ip:
    Spawn(['ifconfig', interface, ip], call=True)
  else:
    factory.console.info(
        'Not setting IP address for interface %s: already set to %s',
        interface, current_ip)

def GetEthernetIp(interface=None):
  """Returns the IP of interface.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, querying a
    specific interface.

  Returns:
    IP address in string format. None if interface doesn't exist nor
    IP is not assigned.
  """
  ip_address = None
  interface = interface or FindUsableEthDevice(raise_exception=False)
  if interface is None:
    return None
  ip_output = SpawnOutput(['ip', 'addr', 'show', 'dev', interface])
  match = re.search('^\s+inet ([.0-9]+)', ip_output, re.MULTILINE)
  if match:
    ip_address = match.group(1)
  return ip_address

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
    raise Error(
        'Timeout when running DHCP command, check if cable is connected.')
  finally:
    dhcp_process.close()

def SendDhcpRequest(interface=None):
  """Sends dhcp request via dhclient.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, operation on a
    specific interface.
  """
  interface = interface or FindUsableEthDevice(raise_exception=True)
  Ifconfig(interface, True)
  _SendDhclientCommand([], interface,
                       expect_str=r"bound to (\d+\.\d+\.\d+\.\d+)")

def ReleaseDhcp(interface=None):
  """Releases a dhcp lease via dhclient.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, operation on a
    specific interface.
  """
  interface = interface or FindUsableEthDevice(raise_exception=True)
  Ifconfig(interface, True)
  _SendDhclientCommand(['-r'], interface)

def PollForCondition(condition, timeout=10,
                     poll_interval_secs=0.1, condition_name=None):
  """Polls for every interval seconds until the condition is met.

  It is a blocking call. The exit conditions are either the condition is met
  or the timeout is reached.

  Args:
    condition: an boolean method without args to be polled. The method can
        return either a boolean or a tuple if additional information need to
        be passed to caller. If a tuple is returned, first element will be
        checked as the boolean result.
    timeout: maximum number of seconds to wait, None means forever.
    poll_interval_secs: interval to poll condition.
    condition_name: description of the condition. Used for TimeoutError when
        timeout is reached.

  Raises:
    TimeoutError.
  """
  start_time = time.time()
  while True:
    ret = condition()
    boolean_result = ret[0] if type(ret) == tuple else ret
    if boolean_result is True:
      return ret
    if timeout and time.time() + poll_interval_secs - start_time > timeout:
      if condition_name:
        condition_name = 'Timed out waiting for condition: %s' % condition_name
      else:
        condition_name = 'Timed out waiting for unnamed condition'
      logging.error(condition_name)
      raise TimeoutError(condition_name)
    time.sleep(poll_interval_secs)


def PrepareNetwork(ip, force_new_ip=False):
  """High-level API to prepare networking.

  1. Wait for presence of ethernet connection (e.g., plug-in ethernet dongle).
  2. Setup IP.

  The operation may block for a long time. Do not run it in UI thread.

  Args:
    ip: The ip address to set. (Set to None if DHCP is used.)
    force_new_ip: Force to set new IP addr regardless of existing IP addr.
  """
  def _obtain_IP():
    if ip is None:
      SendDhcpRequest()
    else:
      SetEthernetIp(ip, force=force_new_ip)
    return True if GetEthernetIp() else False

  factory.console.info('Detecting Ethernet device...')
  try:
    PollForCondition(
        condition=lambda: True if FindUsableEthDevice() else False,
        timeout=INSERT_ETHERNET_DONGLE_TIMEOUT,
        condition_name='Detect Ethernet device')

    current_ip = GetEthernetIp(FindUsableEthDevice())
    if not current_ip or force_new_ip:
      factory.console.info('Setting up IP address...')
      PollForCondition(condition=_obtain_IP, timeout=DEFAULT_TIMEOUT,
                       condition_name='Setup IP address')
  except:  # pylint: disable=W0702
    exception_string = FormatExceptionOnly()
    factory.console.error('Unable to setup network: %s', exception_string)
  factory.console.info('Network prepared. IP: %r', GetEthernetIp())


def GetWLANMACAddress():
  """Returns the MAC address of the first wireless LAN device.

  Returns:
    A string like "de:ad:be:ef:11:22".

  Raises:
    IOError: If unable to determine the MAC address.
  """
  for dev in ['wlan0', 'mlan0']:
    path = '/sys/class/net/%s/address' % dev
    if os.path.exists(path):
      with open(path) as f:
        return f.read().strip()

  raise IOError('Unable to determine WLAN MAC address')

def GetWLANInterface():
  """Returns the interface for wireless LAN device.

  Returns:
    'mlan0' or 'wlan0' depends on the interface name.
    None if there is no wireless interface.
  """
  for dev in ['wlan0', 'mlan0']:
    path = '/sys/class/net/%s/address' % dev
    if os.path.exists(path):
      return dev
  return None

def GetEthernetInterfaces():
  """Returns the interfaces for Ethernet.

  Returns:
    A list like ['eth0', 'eth1'] if those Ethernet interfaces are available.
    Or return [] if there is no Ethernet interface.
  """
  return [os.path.basename(path) for path in glob.glob('/sys/class/net/eth*')]

def SwitchEthernetInterfaces(enable):
  """Switches on/off all Ethernet interfaces.

  Args:
    enable: True to turn up, False to turn down.
  """
  devs = GetEthernetInterfaces()
  for dev in devs:
    Ifconfig(dev, enable)
