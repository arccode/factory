# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

import codecs
import fnmatch
import glob
import http.client
import logging
import os
import random
import re
import socket
import socketserver
import struct
import time
import xmlrpc.client

from six.moves import xrange

from . import file_utils
from . import process_utils
from .type_utils import Error


DEFAULT_TIMEOUT = 10
# Some systems map 'localhost' to its IPv6 equivalent ::1.  Sometimes this
# causes unexpected behaviour.  We want to force the numerical IPv4 address, so
# that these systems run tests under IPv4.
LOCALHOST = '127.0.0.1'
INADDR_ANY = '0.0.0.0'
MAX_PORT = 65535
FULL_MASK = 2 ** 32 - 1
FULL_MASK6 = 2 ** 128 - 1
# https://freedesktop.org/wiki/Software/systemd/PredictableNetworkInterfaceNames
DEFAULT_ETHERNET_NAME_PATTERNS = ['eno*', 'ens*', 'enp*s*', 'enx*', 'eth*']
UNUSED_PORT_LOW = 8192
UNUSED_PORT_HIGH = 32768


class IP(object):
  """A class representing IP addresses, provide some conversion methods."""
  def __init__(self, obj, family=4):
    """Constructor.

    Args:
      obj: either string representation or integer representation of an IP.
    """
    if isinstance(obj, int):
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
    return int(codecs.encode(socket.inet_pton(self.family, self._ip), 'hex'),
               16)

  def __str__(self):
    return self._ip

  def __eq__(self, obj):
    return self._ip == obj._ip  # pylint: disable=protected-access

  def IsIn(self, cidr):
    """Checks the IP is contained in CIDR."""
    netmask = int(cidr.Netmask())
    return int(self) & netmask == int(cidr.IP) & netmask


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

    if isinstance(prefix, int):
      self.prefix = prefix
    else:
      raise RuntimeError('invalid prefix: %s' % prefix)

  def __repr__(self):
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

  def IsOverlapped(self, other):
    my_start = int(self.SelectIP(0))
    my_end = int(self.SelectIP(-1))
    other_start = int(other.SelectIP(0))
    other_end = int(other.SelectIP(-1))

    return (my_start <= other_start <= my_end or
            other_start <= my_start <= other_end)


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


class TimeoutXMLRPCTransport(xmlrpc.client.Transport):
  """Transport subclass supporting timeout."""

  def __init__(self, timeout=DEFAULT_TIMEOUT, *args, **kwargs):
    xmlrpc.client.Transport.__init__(self, *args, **kwargs)
    self.timeout = timeout

  def make_connection(self, host):
    conn = http.client.HTTPConnection(host, timeout=self.timeout)
    return conn


class TimeoutXMLRPCServerProxy(xmlrpc.client.ServerProxy):
  """XML/RPC ServerProxy supporting timeout."""

  def __init__(self, uri, timeout=10, *args, **kwargs):
    if timeout:
      kwargs['transport'] = TimeoutXMLRPCTransport(
          timeout=timeout)
    xmlrpc.client.ServerProxy.__init__(self, uri, *args, **kwargs)


def FindUsableEthDevice(raise_exception=False,
                        name_patterns=DEFAULT_ETHERNET_NAME_PATTERNS):
  # pylint: disable=dangerous-default-value
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
  devices = GetEthernetInterfaces(name_patterns)
  for dev in devices:
    p = process_utils.Spawn('ethtool %s' % dev, shell=True, read_stdout=True,
                            ignore_stderr=True)
    stat = p.stdout_data

    # A 4G introduced ethernet interface would not be able to report its
    # setting data because it won't get online during the factory flow.
    # In case that there are several real ethernet interfaces available,
    # we favor the one that has the cable connected end-to-end.
    current_level = 0
    if 'Supported ports:' in stat:
      current_level += 1
    # For Linksys USB-Ethernet Adapter, it won't have 'Supported ports' field
    # So we also give weight to 'Link detected: yes'
    if 'Link detected: yes' in stat:
      current_level += 2
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
      if isinstance(netmask, int):
        netmask = str(CIDR(ip, netmask).Netmask())
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
  return (ip_address, prefix_number)

def SetAliasEthernetIp(ip, alias_index=0, interface=None, mask='255.255.255.0'):
  """Sets the alias IP address for Ethernet.

  Args:
    ip: The ip address want to set.
    alias_index: Alias interface index.
    interface: The target interface.
    mask: Network mask.
  """
  interface = interface or FindUsableEthDevice(raise_exception=False)
  alias_interface = '%s:%d' % (interface, alias_index)
  process_utils.Spawn(['ifconfig', alias_interface, ip, 'netmask', mask, 'up'],
                      call=True, log=True)

def UnsetAliasEthernetIp(alias_index=0, interface=None):
  """UnSets the alias IP address for Ethernet.

  Args:
    alias_index: Alias interface index.
    interface: The target interface.
  """
  interface = interface or FindUsableEthDevice(raise_exception=False)
  alias_interface = '%s:%d' % (interface, alias_index)
  process_utils.Spawn(['ifconfig', alias_interface, 'down'],
                      call=True, log=True)


def GetNetworkInterfaceByPath(interface_path, allow_multiple=False):
  """Gets the name of the network interface.

  The name of network interface created by USB dongle is unstable. This function
  gets the current interface name of a certain USB port.

  For example:
    # realpath /sys/class/net/eth0
    /sys/devices/pci0000:00/0000:00:14.0/usb1/1-5/1-5:1.0/net/eth0
  Then
    GetInterfaceName(
        '/sys/devices/pci0000:00/0000:00:14.0/usb1/1-5/1-5:1.0/net') => 'eth0'

  interface_path can also be a pattern.  The realpath of a interface will be
  matched with the pattern you provided by 'fnmatch'.

  Args:
    interface_path: the name of the network interface or the realpath of the
      network interface sysfs node or the pattern that realpath should match.

  Returns:
    the name of the network interface. None if the path is not found.

  Raises:
    ValueError if allow_multiple is False and multiple interfaces are found.
  """
  if interface_path[0] != '/':  # The name of the network interface.
    return interface_path
  valid_interfaces = []

  for path in glob.glob('/sys/class/net/*'):
    realpath = os.path.realpath(path)
    if (realpath.startswith(interface_path) or
        fnmatch.fnmatch(realpath, interface_path)):
      interface = os.path.basename(path)
      logging.info('Interface "%s" is found.', interface)
      valid_interfaces.append(interface)
  if not valid_interfaces:
    logging.warning('No interface is found.')
    return None
  if len(valid_interfaces) == 1:
    return valid_interfaces[0]
  if allow_multiple:
    logging.warning('Multiple interfaces are found: %s', valid_interfaces)
    return valid_interfaces[0]
  else:
    raise ValueError('Multiple interfaces are found: %s' % valid_interfaces)


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


def GetEthernetInterfaces(name_patterns=DEFAULT_ETHERNET_NAME_PATTERNS):
  # pylint: disable=dangerous-default-value
  """Returns the interfaces for Ethernet.

  Args:
    name_patterns: A list that contains all name patterns of ethernet
                   interfaces.

  Returns:
    A list like ['eth0', 'eth1'] if those Ethernet interfaces are available.
    Or return [] if there is no Ethernet interface.
  """
  interfaces = []
  for name in name_patterns:
    interfaces += [os.path.basename(path)
                   for path in glob.glob(os.path.join('/sys/class/net', name))]
  return interfaces


def SwitchEthernetInterfaces(enable,
                             name_patterns=DEFAULT_ETHERNET_NAME_PATTERNS):
  # pylint: disable=dangerous-default-value
  """Switches on/off all Ethernet interfaces.

  Args:
    enable: True to turn up, False to turn down.
  """
  devs = GetEthernetInterfaces(name_patterns)
  for dev in devs:
    Ifconfig(dev, enable)


def ExistPluggedEthernet(name_patterns=None):
  """Check for plugged in network cable by /sys/class/net/<ethernet>/carrier.

  Return True if exists an ethernet with carrier > 0. False if none.
  """
  devs = GetEthernetInterfaces(name_patterns or DEFAULT_ETHERNET_NAME_PATTERNS)
  for dev in devs:
    if int(file_utils.ReadFile('/sys/class/net/%s/carrier' % dev)) > 0:
      return True
  return False


def FindUnusedPort(tcp_only=False, length=1):
  """Finds a range of semi-random available port.

  A race condition is still possible after the port number is returned, if
  another process happens to bind it.

  This is ported from autotest repo.

  Arguments:
    tcp_only: Whether to only find port that is free on TCP.
    length: The length of the range.

  Returns:
    A port number that [port, ..., port + length - 1] is unused on TCP (and
    UDP, if tcp_only is False).
  """

  def _GetRandomPort():
    # The environ would be set by tools/run_tests.py, and would point to a unix
    # stream server that can be used to ensure unittests in different processes
    # would not get same random port, thus eliminate the chance of race
    # condition between different unit tests.
    addr = os.environ.get('CROS_FACTORY_UNITTEST_PORT_DISTRIBUTE_SERVER')
    if addr:
      sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
      try:
        sock.connect(addr)
        sock.send(struct.pack('B', length))
        port = struct.unpack('<H', sock.recv(2))[0]
        logging.debug('Got port %d from port distribute server.', port)
        return port
      except Exception:
        pass
      finally:
        sock.close()
    return random.randrange(UNUSED_PORT_LOW, UNUSED_PORT_HIGH)

  def TryBind(port, socket_type, socket_proto):
    # If python support IPV6, then we use AF_INET6 to bind to both IPv4 and
    # IPv6, so the returned port would be unused for both. If python doesn't,
    # we only bind IPV4.
    socket_family = socket.AF_INET6 if socket.has_ipv6 else socket.AF_INET
    s = socket.socket(socket_family, socket_type, socket_proto)
    try:
      try:
        s.bind(('', port))
        return True
      except socket.error:
        return False
    finally:
      s.close()

  def _CheckPort(port):
    if TryBind(port, socket.SOCK_STREAM, socket.IPPROTO_TCP):
      # Check if this port is unused on the other protocol.
      if tcp_only or TryBind(port, socket.SOCK_DGRAM, socket.IPPROTO_UDP):
        return True
    return False

  # We don't bind to port 0 and use the port given by kernel, since the port
  # would be in ephemeral port range, and the chance of it to confilct with
  # other code because of race condition would be larger since it would
  # possibly be conflicting with port used by outgoing connection too.
  #
  # Also, a typical usage of FindUnusedPort is as follows:
  #   port = net_utils.FindUnusedPort()
  #   server = StartServerAsync(port=port)
  #   sync_utils.WaitFor(lambda: PingServer(port=port), 2)
  # But if the server port is in ephemeral port range, there's a small chance
  # that the PingServer() would actually connects to itself, binding the port,
  # and the StartServerAsync() would fail.
  # (See http://sgros.blogspot.tw/2013/08/tcp-client-self-connect.html)
  while True:
    port = _GetRandomPort()
    if all(_CheckPort(p) for p in range(port, port + length)):
      logging.info('FindUnusedPort returned port %d (length = %d)', port,
                   length)
      return port


def FindUnusedTCPPort():
  """Returns a TCP port that is unused on all interfaces for testing.

  There would always be a time window between checking a port is unused to
  actually binding the port, that would cause race condition if other use this
  port in between. So this method should be considered as a convenient method
  for use in testing.

  If race condition need to be avoided, caller should bind to port 0 directly,
  and the kernel would do the right job.
  """
  return FindUnusedPort(tcp_only=True)


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
      raise ValueError('Invalid port number: %r' % port)
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
  Kernel IP routing table
  Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
  0.0.0.0         192.168.0.1     0.0.0.0         UG    600    0        0 wlan0

  Flag UG means the route is Up, and it's the Gateway.

  Returns:
    The default gateway interface if it exists.

  Raises:
    ValueError if the output of `route -n` is unexpected.
  """
  output = process_utils.CheckOutput(['route', '-n'])
  lines = output.splitlines()

  # Find the title line.
  for line_idx, line in enumerate(lines):
    try:
      title = line.split()
      flag_idx = title.index('Flags')
      iface_idx = title.index('Iface')
      dest_idx = title.index('Destination')
      break
    except ValueError:
      pass
  else:
    raise ValueError('Output of `route -n` is unexpected.\n%s' % output)

  for line in lines[line_idx + 1:]:  # pylint: disable=undefined-loop-variable
    data = line.split()
    if len(data) < max(flag_idx, iface_idx, dest_idx):
      continue
    if data[flag_idx] == 'UG' and data[dest_idx] == '0.0.0.0':
      return data[iface_idx]
  return None


def GetUnusedIPV4RangeCIDR(preferred_prefix_bits=24, exclude_ip_prefix=None,
                           exclude_local_interface_ip=False,
                           max_prefix_bits=30):
  """Find unused IP ranges in IPV4 private address space.

  Args:
    preferred_prefix_bits: The preferred prefix length in bits.
    exclude_ip_prefix: A list of tuple of (ip, prefix_bits) to exclude.
    exclude_local_interface_ip: Also exclude IP used by the local interface.
    max_prefix_bits: the maximum prefix length in bits.

  Returns:
    A CIDR object representing the network range.
  """
  IPV4_PRIVATE_RANGE = [
      CIDR('10.0.0.0', 8),
      CIDR('172.16.0.0', 12),
      CIDR('192.168.0.0', 16)
  ]

  exclude_ip_prefix = exclude_ip_prefix or []

  # Exclude local interface IP, populate it with all the ip/prefix currently on
  # the machine interfaces.
  if exclude_local_interface_ip:
    for iface in GetNetworkInterfaces():
      ip_mask = GetEthernetIp(iface, True)
      if ip_mask[0] and ip_mask[1]:
        exclude_ip_prefix.append(ip_mask)

  occupied_list = [CIDR(ip, prefix_bits)
                   for (ip, prefix_bits) in exclude_ip_prefix]
  occupied_list.sort(key=lambda cidr: int(cidr.SelectIP(0)))

  # starting from preferred_prefix_bits, try to find an subnet that are
  # available. If we can't, increase the prefix_bits, i.e., find a smaller
  # subnet.
  for prefix_bits in xrange(preferred_prefix_bits, max_prefix_bits + 1):
    step = 2 ** (32 - prefix_bits)
    for ip_range in IPV4_PRIVATE_RANGE:
      # we split this private range into several subnets according to
      # prefix_bits, and find a subnet is entirely available.
      # since occupied_list is ordered in incremental order, so for each subnet,
      # we don't need to check entire occpuied_list, we only need to start from
      # previous failed item.

      # next subnet in occupied_list to check
      occupied_list_idx = 0

      start = int(ip_range.SelectIP(0))
      while True:
        cidr = CIDR(IP(start), prefix_bits)  # current subnet
        if int(cidr.SelectIP(-1)) > int(ip_range.SelectIP(-1)):
          # current subnet excceed ip_range
          break

        valid_range = True
        while occupied_list_idx < len(occupied_list):
          if cidr.IsOverlapped(occupied_list[occupied_list_idx]):
            valid_range = False
            break
          else:
            # check next subnet in occupied_list
            occupied_list_idx += 1
        if valid_range:
          return cidr
        start = max(start + step,
                    int(occupied_list[occupied_list_idx].SelectIP(-1)) + 1)
        if start % step != 0:
          start = (start // step + 1) * step

  raise RuntimeError('can not find unused IP range')


class WLAN(object):
  """Class for wireless network settings.

  This class is used in test lists to specify WLAN settings for the
  connection manager.
  """

  def __init__(self, ssid=None, security='none', passphrase=''):
    """Constructor.

    Please see 'http://code.google.com/searchframe#wZuuyuB8jKQ/src/third_party/
    flimflam/doc/service-api.txt' for a detailed explanation of these
    parameters.

    Note the instance of this class may be serialized via JSONRPC, so a default
    constructor without parameter must be allowed (jsonrpc calls __setstate__
    instead of constructor).

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
    if security not in ['none', 'wep', 'rsn', 'psk', '802_1x']:
      raise ValueError('Invalid wireless network security type: %s'
                       % security)
    self.ssid = ssid
    self.security = security
    self.passphrase = passphrase


class CallbackSocketServer(object):
  @staticmethod
  def RequestHandlerFactory(callback):
    class _Handler(socketserver.StreamRequestHandler):
      def handle(self):
        callback(self)
    return _Handler

  class _ThreadedTCPServer(socketserver.TCPServer):
    pass

  def __init__(self, callback):
    # bind on arbitrary unused port and all network interfaces
    self._server = CallbackSocketServer._ThreadedTCPServer(
        ('', 0), CallbackSocketServer.RequestHandlerFactory(callback))
    unused_ip, port = self._server.server_address
    EnablePort(port)

  def __getattr__(self, name):
    return getattr(self._server, name)


def _ProbePort(address, socket_family, socket_type):
  s = socket.socket(socket_family, socket_type)
  try:
    s.connect(address)
    return True
  except socket.error:
    return False
  finally:
    s.close()


def ProbeTCPPort(address, port):
  """Probes whether a TCP connection can be made to the given address and port.

  Args:
    address: The IP address to probe.
    port: The port to probe.
  """
  return _ProbePort((address, port), socket.AF_INET, socket.SOCK_STREAM)


def ShutdownTCPServer(server):
  """Shutdown a TCPServer in serve_forever loop in another thread.

  This is done by setting shutdown flag, and connect to the server to wake up
  the select in serve_forever, so the shutdown can run faster than
  poll_interval.
  """
  # pylint: disable=protected-access
  server._BaseServer__shutdown_request = True
  _ProbePort(server.server_address, server.address_family, server.socket_type)
  server._BaseServer__is_shut_down.wait()


def GetDefaultGatewayIP():
  """Gets address of the default gateway."""
  # An easy way to get IP of the default gateway. It's possible to use python
  # packages such as netifaces or pynetinfo, but on DUT shill may override the
  # behavior of them.
  return IP(process_utils.CheckOutput(
      'ip route | grep "^default"', shell=True).split()[2])


_cached_docker_host_ip = None
def GetDockerHostIP(force_reload=False):
  """Gets address of the Docker host inside a container.

  Args:
    force_reload: boolean. If False, the function will try to use cached value
      when possible. Otherwise, (True or cache is None), will force reload.
  """
  global _cached_docker_host_ip  # pylint: disable=global-statement
  if force_reload or not _cached_docker_host_ip:
    _cached_docker_host_ip = GetDefaultGatewayIP()
  return _cached_docker_host_ip
