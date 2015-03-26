# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

import SocketServer

import glob
import httplib
import logging
import os
import re
import socket
import struct
import subprocess
import time
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import Error


DEFAULT_TIMEOUT = 10
# Some systems map 'localhost' to its IPv6 equivalent ::1.  Sometimes this
# causes unexpected behaviour.  We want to force the numerical IPv4 address, so
# that these systems run tests under IPv4.
LOCALHOST = '127.0.0.1'
MAX_PORT = 65535
FULL_MASK = 2 ** 32 - 1
FULL_MASK6 = 2 ** 128 - 1


class IP(object):
  """A class representing IP addresses, provide some conversion methods."""
  def __init__(self, obj, family=4):
    """Constructor.

    Args:
      obj: either string representation or integer representation of an IP.
    """
    if isinstance(obj, int) or isinstance(obj, long):
      if family == 4:
        self.family = socket.AF_INET
        self._ip = socket.inet_ntop(self.family, struct.pack('>I', obj))
      elif family == 6:
        self.family = socket.AF_INET6
        ip_bytes = struct.pack('>2Q', obj >> 64, obj & (FULL_MASK6 >> 64))
        self._ip = socket.inet_ntop(self.family, ip_bytes)
      else:
        raise RuntimeError('invalid inet family assignment')
    elif isinstance(obj, str):
      try:
        socket.inet_pton(socket.AF_INET, obj)
      except socket.error:
        try:
          socket.inet_pton(socket.AF_INET6, obj)
        except socket.error:
          raise RuntimeError('invalid ip string')

      self._ip = obj
      self.family = socket.AF_INET if '.' in self._ip else socket.AF_INET6
    else:
      raise RuntimeError('invalid argument to IP __init__ function')

  def __int__(self):
    """Convert IP string to integer representation."""
    return int(socket.inet_pton(self.family, self._ip).encode('hex'), 16)

  def __str__(self):
    return self._ip

  def __eq__(self, obj):
    return self._ip == obj._ip  # pylint: disable=W0212


class CIDR(object):
  """A class storing IP ranges in the CIDR format."""
  def __init__(self, ip, prefix):
    """Constructor.

    Args:
      ip: either an IP object, or IP string.
      prefix: the CIDR prefix number.
    """
    if isinstance(ip, str):
      self.IP = IP(ip)
    elif isinstance(ip, IP):
      self.IP = ip
    else:
      raise RuntimeError('invalid ip argument in constructor')
    self.prefix = prefix

  def __str__(self):
    return '%s/%d' % (self.IP, self.prefix)

  def __eq__(self, obj):
    return self.IP == obj.IP and self.prefix == obj.prefix

  def SelectIP(self, n=0):
    """Select IP within the CIDR network range.

    Args:
      n: select the n-th IP. If n is a negative value, the selection is done
      from the end, i.e. select the last n-th IP.
    """
    if self.IP.family != socket.AF_INET:
      raise RuntimeError('only IPv4 address selction is supported for now')

    ip_int = int(self.IP) & int(self.Netmask())
    host_bits = 32 - self.prefix

    if abs(n) > 2 ** host_bits - 1:
      raise RuntimeError('selection beyond IP range')

    return IP(ip_int | n) if n >= 0 else IP(ip_int | (2 ** host_bits + n))

  def Netmask(self):
    full_mask = FULL_MASK if self.IP.family == socket.AF_INET else FULL_MASK6
    return IP(full_mask ^ (full_mask >> self.prefix))


def Ifconfig(devname, enable, sleep_time_secs=1):
  """Brings up/down interface.

  Args:
    devname: Device name.
    enable: True is to bring up interface. False is down.
    sleep_time_secs: The sleeping time after ifconfig up.
  """
  process_utils.Spawn(['ifconfig', devname, 'up' if enable else 'down'],
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


def SetEthernetIp(ip, interface=None, netmask=None, force=False, logger=None):
  """Sets the IP address for Ethernet.

  Args:
    ip: The ip address want to set.
    interface: The target interface. The interface will be automatically
        assigned by Connection Manager if None is given.
    netmask: The netmask to set.
    force: If force is False, the address is set only if the interface
        does not already have an assigned IP address.
    logger: A callback function to send verbose messages.
  """
  interface = interface or FindUsableEthDevice(raise_exception=True)
  Ifconfig(interface, True)
  current_ip = GetEthernetIp(interface)
  if force or not current_ip:
    cmd = ['ifconfig', interface, ip]
    if netmask:
      cmd += ['netmask', netmask]
    process_utils.Spawn(cmd, call=True)
  elif logger:
    logger('Not setting IP address for interface %s: already set to %s' %
           (interface, current_ip))


def GetEthernetIp(interface=None, netmask=False):
  """Returns the IP of interface.

  Args:
    interface: None to use FindUsableEthDevice, otherwise, querying a
    specific interface.
    netmask: Whether or not to return netmask.

  Returns:
    IP address in string format. If netmask=True, returns a tuple
    (IP address string, preifx number).  None or (None, None) if interface
    doesn't exist nor IP is not assigned
  """
  ip_address = None
  prefix_number = None
  interface = interface or FindUsableEthDevice(raise_exception=False)
  if interface is None:
    return None
  ip_output = process_utils.SpawnOutput(
      ['ip', 'addr', 'show', 'dev', interface])
  match = re.search(r'^\s+inet ([.0-9]+)/([0-9]+)', ip_output, re.MULTILINE)
  if match:
    ip_address = match.group(1)
    prefix_number = int(match.group(2))

  if not netmask:
    return ip_address
  else:
    return (ip_address, prefix_number)


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


def GetNetworkInterfaces():
  """Returns all network interfaces.

  Returns:
    A list like ['eth0', 'eth1', 'wlan0'] Or return [] if there is no other
    network interface.
  """
  return [os.path.basename(path) for path in glob.glob('/sys/class/net/*')
          if os.path.basename(path) != 'lo']


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


def IsPortBeingUsed(port):
  """Checks if a port is being used.

  Args:
    port: A port number to check.

  Returns:
    True if the port is being used.
  """
  ret = process_utils.Spawn(['lsof', '-i', ':%d' % port],
                            call=True, sudo=True).returncode
  return True if ret == 0 else False


def FindConsecutiveUnusedPorts(port, length):
  """Finds a range of ports that are all available.

  Args:
    port: The port number of starting port to search.
    length: The length of the range.

  Returns:
    A port number such that [port, port + 1,..., port+length-1] are all
    available.
  """
  success_count = 0
  current_port = port
  while current_port < MAX_PORT:
    if not IsPortBeingUsed(current_port):
      success_count = success_count + 1
      if success_count == length:
        starting_port = current_port - length + 1
        logging.info('Found valid port %r ~ %r', starting_port, current_port)
        return starting_port
    else:
      success_count = 0
    current_port = current_port + 1
  raise Exception(
      'Can not find a range of valid ports from %s to %s' % (
          current_port, MAX_PORT))


def GetUnusedPort():
  """Finds a semi-random available port.

  A race condition is still possible after the port number is returned, if
  another process happens to bind it.

  This is ported from autotest repo.

  Returns:
    A port number that is unused on both TCP and UDP.
  """

  def TryBind(port, socket_type, socket_proto):
    s = socket.socket(socket.AF_INET, socket_type, socket_proto)
    try:
      try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', port))
        return s.getsockname()[1]
      except socket.error:
        return None
    finally:
      s.close()

  # On the 2.6 kernel, calling TryBind() on UDP socket returns the
  # same port over and over. So always try TCP first.
  while True:
    # Ask the OS for an unused port.
    port = TryBind(0, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    # Check if this port is unused on the other protocol.
    if port and TryBind(port, socket.SOCK_DGRAM, socket.IPPROTO_UDP):
      return port


def FindUnusedTCPPort():
  """Returns an unused TCP port for testing."""
  server = SocketServer.TCPServer((LOCALHOST, 0),
                                  SocketServer.BaseRequestHandler)
  return server.server_address[1]


def EnablePort(port, protocol='tcp', priority=None, interface=None):
  """Allows incoming connection from remote hosts to given port.

  Configures system firewall (iptables) to allow remote connection.

  Args:
    port: A number (1~MAX_PORT) for connection port, or None for all packets.
    protocol: A string for network protocol (ex, 'tcp' or 'udp').
    priority: A number for rule priority (1 is highest) or None as lowest.
    interface: A string for network interface. None to enable all interfaces.

  Raises:
    ValueError: When given parameters are invalid.
  """
  command = 'iptables'
  rule = []
  if (not protocol) and port:
    # Ports are not allowed if protocol is omitted.
    raise ValueError('Cannot assign port %r without protocol.' % port)
  if protocol:
    rule += ['-p', protocol]
  if port:
    if (port < 1) or (port > MAX_PORT):
      raise ValueError('Invalid port number: %r', port)
    rule += ['--dport', str(port)]
  if interface:
    rule += ['-i', interface]
  rule += ['-j', 'ACCEPT']

  rule_exists = not process_utils.Spawn(
      ['iptables', '-C', 'INPUT'] + rule, call=True,
      ignore_stderr=True).returncode
  if priority is None:
    # Only add if rule exists.
    if not rule_exists:
      process_utils.Spawn([command, '-A', 'INPUT'] + rule, check_call=True)
  else:
    # Delete existing rules and insert at target location.
    if rule_exists:
      process_utils.Spawn([command, '-D', 'INPUT'] + rule, check_call=True)
    process_utils.Spawn([command, '-I', 'INPUT', str(priority)] + rule,
                        check_call=True)


def StartNATService(interface_in, interface_out):
  """Starts NAT service.

  This method configures the IP filter/forward rules to set up a NAT
  service. The traffic coming in from 'interface_in' will be routed
  to 'interface_out'.

  Args:
    interface_in: The interface that goes 'in'. That is, the interface
      that is connected to the network that needs address translation.
    interface_out: The interface that goes 'out'. For example, the
      factory network.
  """
  def CallIptables(args):
    process_utils.LogAndCheckCall(['sudo', 'iptables'] + args)

  if not isinstance(interface_in, list):
    interface_in = [interface_in]

  # Clear everything in 'nat' table
  CallIptables(['--table', 'nat', '--flush'])
  CallIptables(['--table', 'nat', '--delete-chain'])

  # Clear FORWARD rules in 'filter' table
  CallIptables(['--flush', 'FORWARD'])

  # Configure NAT
  CallIptables(['--table', 'nat',
                '--append', 'POSTROUTING',
                '--out-interface', interface_out,
                '-j', 'MASQUERADE'])
  # Allow new connections
  for interface in interface_in:
    CallIptables(['--append', 'FORWARD',
                  '--out-interface', interface_out,
                  '--in-interface', interface,
                  '--match', 'conntrack',
                  '--ctstate', 'NEW',
                  '-j', 'ACCEPT'])
  # Allow established connection packets
  CallIptables(['--append', 'FORWARD',
                '--match', 'conntrack',
                '--ctstate', 'ESTABLISHED,RELATED',
                '-j', 'ACCEPT'])

  # Enable routing in kernel
  file_utils.WriteFile('/proc/sys/net/ipv4/ip_forward', '1')


def GetDefaultGatewayInterface():
  """Return the default gateway interface.

  `route -n` has the output in the form of:
  Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
  0.0.0.0         192.168.0.1     0.0.0.0         UG    600    0        0 wlan0

  Flag UG means the route is Up, and it's the Gateway. We can simply extract the
  eighth column `Iface` to get the default gateway interface.
  """
  output = process_utils.CheckOutput('route -n | grep UG', shell=True)
  if output:
    return output.split()[7]
  else:
    raise RuntimeError('no default gateway found')


def GetUnusedIPV4RangeCIDR(preferred_prefix_bits=24, exclude_ip_prefix=None):
  """Find unused IP ranges in IPV4 private address space.

  Args:
    preferred_prefix_bits: the preferred prefix length in bits
    exclude_ip_prefix: A list of tuple of (ip, prefix_bits) to exclude.

  Returns:
    A CIDR object representing the network range.
  """
  IPV4_PRIVATE_RANGE = [
      CIDR('10.0.0.0', 8),
      CIDR('172.16.0.0', 12),
      CIDR('192.168.0.0', 16)
  ]

  # If no exclude_ip_prefix is specified, populate it with all the ip/prefix
  # currently on the machine interfaces.
  if not exclude_ip_prefix:
    exclude_ip_prefix = []
    for iface in GetNetworkInterfaces():
      ip_mask = GetEthernetIp(iface, True)
      if ip_mask[0] and ip_mask[1]:
        exclude_ip_prefix.append(ip_mask)

  # available_ranges_bits stores (ip_range, available_subnet_range_bits)
  # For example: available_ranges_bits = {0xc0a80000: 8}
  # means we have 8 bits of subnet range 192.168.[0-255].0/24
  available_ranges_bits = dict((int(x.IP), preferred_prefix_bits - x.prefix)
                               for x in IPV4_PRIVATE_RANGE)

  # used_subnet_range stores (ip_range, used_subnet ranges)
  # For example: if there are two interfaces with IP 192.168.0.1/24,
  # 192.168.1.1/24, this means available_ranges_bits [0xc0a80000] = 8
  # used_subnet_range = {0xc0a80000: [0, 1]}.
  used_subnet_range = dict((int(x.IP), []) for x in IPV4_PRIVATE_RANGE)

  for ip_str, prefix_bits in exclude_ip_prefix:
    # Select the min of (prefix_bits, preferred_prefix_bits). For example:
    # if 192.168.0.0/16 (prefix_bits=16) is used, and preferred_prefix_bits=24.
    # Since the entire /16 range is unavailable, we can't use any /24 ranges.
    selected_prefix_bits = min(prefix_bits, preferred_prefix_bits)
    excluded_ip = int(IP(ip_str))

    for cidr in IPV4_PRIVATE_RANGE:
      mask = int(cidr.Netmask())
      ip = int(cidr.IP)
      base_prefix_bits = cidr.prefix
      range_bits = selected_prefix_bits - base_prefix_bits

      # If the IP is in the same range as the current IPV4_PRIVATE_RANGE.
      if excluded_ip & mask == ip:
        if range_bits < available_ranges_bits[ip]:
          # Target target IP has range smaller then previous stored range bit,
          # so previous record is invalid, create a new list.
          #
          # This happens when exclude_ip_prefix = [('10.0.0.1', 24),
          # ('10.0.0.2', 16)]. At first range_bits = 24 - 8 = 16, means we have
          # 16 bit for different subnet. Later when the second target comes in,
          # range_bits = 16 - 8 = 8, means we only have 8 bit of subnet ranges
          # left.
          available_ranges_bits[ip] = range_bits
          used_subnet_range[ip] = [(excluded_ip & (mask ^ FULL_MASK)) >>
                                   (32 - selected_prefix_bits)]
        elif range_bits == available_ranges_bits[ip]:
          # The target IP has same range with the available_ranges_bits, append
          # the used range to the used_subnet_range.
          used_subnet_range[ip].append((excluded_ip & (mask ^ FULL_MASK)) >>
                                       (32 - selected_prefix_bits))
        break

  for cidr in IPV4_PRIVATE_RANGE:
    ip = int(cidr.IP)
    subnet_range_bits = available_ranges_bits[ip]
    # if subnet_range_bits == 0 means the entire range is used out.
    if subnet_range_bits > 0:
      # Iterate through all avaialble subnet range, pick one that is not used.
      for i in range(0, 2 ** subnet_range_bits - 1):
        if i not in used_subnet_range[ip]:
          prefix_bits = cidr.prefix + subnet_range_bits
          ip_base = ip | i << (32 - prefix_bits)
          return CIDR(IP(ip_base), prefix_bits)

  raise RuntimeError('can not find unused IP range')


class WLAN(object):
  """Class for wireless network settings.

  This class is used in test lists to specify WLAN settings for the
  connection manager.
  """

  def __init__(self, ssid, security, passphrase):
    """Constructor.

    Please see 'http://code.google.com/searchframe#wZuuyuB8jKQ/src/third_party/
    flimflam/doc/service-api.txt' for a detailed explanation of these
    parameters.

    Args:
      ssid: Wireless network SSID.
      security: Wireless network security type. For example:
        "none": no security.
        "wep": fixed key WEP.
        "wpa": WPA-PSK (but see below; use "psk" instead).
        "rsn": IEEE 802.11i-PSK
        "psk": WPA2-PSK[AES], WPA-PSK[TKIP] + WPA2-PSK[AES].
               Also, "wpa" and "rsn" can be replaced by "psk".
        "802_1x": IEEE 802.11i with 802.1x authentication.

        Note that when using "wpa" for WPA2-PSK[AES] or
        WPA-PSK[TKIP] + WPA2-PSK[AES], flimflam can connect but it will always
        cache the first passphrase that works. For this reason, use "psk"
        instead of "wpa". Using "wpa" will result in an explicit exception.
      passphrase: Wireless network password.
    """
    if security == 'wpa':
      raise ValueError('Invalid wireless network security type:'
                       " wpa. Use 'psk' instead")
    if not security in ['none', 'wep', 'rsn', 'psk', '802_1x']:
      raise ValueError('Invalid wireless network security type: %s'
                       % security)
    self.ssid = ssid
    self.security = security
    self.passphrase = passphrase
