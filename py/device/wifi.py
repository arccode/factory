# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""WiFi: DUT API system module to control WiFi device.

WiFi is a DUT API system module to list and connect to WiFi networks.

Three different modules are provided:
- WiFi: Generic WiFi usage.
- WiFiChromeOS: Disables necessary services, and uses dhclient.
- WiFiAndroid: Uses dhcpcd.

The WiFi class can also be subclassed for any future devices with different
requirements.

Example usage::

  ap = dut.wifi.FindAccessPoint(ssid='GoogleGuest')
  print(u'SSID: %s, strength: %.2f dBm' % (ap.ssid, ap.strength))
  conn = dut.wifi.Connect(ap, passkey='my_pass_key')
  conn.Disconnect()
"""

import logging
import os
import re
import textwrap
import time

from cros.factory.device import device_types
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class WiFiError(Exception):
  """Error with some WiFi-related functionality."""


class WiFi(device_types.DeviceComponent):
  """WiFi system component."""
  _SCAN_TIMEOUT_SECS = 20
  _ACCESS_POINT_RE = re.compile(
      r'BSS ([:\w]*)\W*\(on \w*\)( -- associated)?\r?\n')
  _WLAN_NAME_PATTERNS = ['wlan*', 'mlan*']
  _RE_WIPHY = re.compile(r'wiphy (\d+)')
  _RE_LAST_SEEN = re.compile(r'(\d+) ms ago$')

  # Shortcut to access exception object.
  WiFiError = WiFiError

  def __init__(self, dut, tmp_dir=None):
    super(WiFi, self).__init__(dut)
    self.tmp_dir = tmp_dir

  def _NewConnection(self, *args, **kwargs):
    """Creates a new Connection object with the given arguments.

    Can be overridden in a subclass to send custom arguments to the Connection
    class.
    """
    return Connection(*args, dhcp_method=Connection.DHCP_DHCPCD, **kwargs)

  def GetInterfaces(self, name_patterns=None):
    """Returns the interfaces for wireless LAN devices.

    Args:
      name_patterns: A list that contains all name patterns of WiFi interfaces.

    Returns:
      A list like ['wlan0', 'mlan0'] if those wireless LAN interfaces are
      available.  Returns [] if there are no wireless LAN interfaces.
    """
    if not name_patterns:
      name_patterns = self._WLAN_NAME_PATTERNS
    interfaces = []
    for pattern in name_patterns:
      interfaces += [self._device.path.basename(path) for path in
                     self._device.Glob('/sys/class/net/' + pattern) or []]
    return interfaces

  def SelectInterface(self, interface=None):
    """Returns an interface for wireless LAN devices.

    Args:
      interface: The specified interface.

    Raises:
      WiFiError if the specified interface is not available or the interface is
      not specified when there are multiple available interfaces.

    Returns:
      An available interface.
    """
    # Check that we have an online WLAN interface.
    interfaces = self.GetInterfaces()

    # Ensure there are WLAN interfaces available.
    if not interfaces:
      raise WiFiError('No available WLAN interfaces.')

    # If a specific interface is specified, check that it exists.
    if interface:
      if interface not in interfaces:
        raise WiFiError('Specified interface %s not available' %
                        interface)
      return interface

    # If no interface is specified, check the uniqueness.
    if len(interfaces) != 1:
      raise WiFiError(
          'There are multiple interfaces. '
          'Please specify one from: %r' % interfaces)
    return interfaces[0]

  def BringsUpInterface(self, interface, sleep_time_secs=1):
    """Brings up interface.

    Args:
      interface: Interface name.
      sleep_time_secs: The sleeping time after bringing up.
    """
    self._device.CheckCall(['ifconfig', interface, 'up'], log=True)
    time.sleep(sleep_time_secs)

  def BringsDownInterface(self, interface, sleep_time_secs=1):
    """Brings up interface.

    Args:
      interface: Interface name.
      sleep_time_secs: The sleeping time after bringing up.
    """
    self._device.CheckCall(['ifconfig', interface, 'down'], log=True)
    time.sleep(sleep_time_secs)

  def DetectPhyName(self, interface):
    """Detects the phy name of interface.

    Returns:
      The phy name of interface.
    """
    output = self._device.CheckOutput(
        ['iw', 'dev', interface, 'info'], log=True)
    m = self._RE_WIPHY.search(output)
    return ('phy' + m.group(1)) if m else None

  def _ValidateInterface(self, interface=None):
    """Returns either provided interface, or one retrieved from system."""
    if interface:
      return interface

    interfaces = self.GetInterfaces()
    if not interfaces:
      raise WiFiError('No available WLAN interfaces.')

    # Arbitrarily choose first interface.
    return interfaces[0]

  def _AllAccessPoints(self, interface, frequency):
    """Retrieves a list of AccessPoint objects.

    Args:
      interface: the interface name to find the access points.

    Returns:
      a list of the found access points objects.
    """
    command = ['iw', 'dev', interface, 'scan']
    if frequency is not None:
      command += ['freq', str(frequency)]
    try:
      # First, bring the device up.  If it is already up, this will succeed
      # anyways.
      self.BringsUpInterface(interface, 0)

      output = self._device.CheckOutput(command, log=True)
      return self._ParseScanResult(output)
    except device_types.CalledProcessError:
      return []

  def _ParseScanResult(self, output):
    """Parses output from iw scan into AccessPoint objects."""
    # Split access points into a list.  Since we split on a string encountered
    # at the very beginning of the output, the first element is blank (thus
    # we skip the first element).  Remaining elements are in groups of three,
    # in groups of: (BSSID, associated, other).
    bssid_ap_list = self._ACCESS_POINT_RE.split(output)[1:]
    bssid_ap_tuples = [bssid_ap_list[x:x+3]
                       for x in range(0, len(bssid_ap_list), 3)]

    # Parse each AP.
    aps = []
    for bssid, associated, ap_data in bssid_ap_tuples:
      active = bool(associated)
      aps.append(self._ParseScanAccessPoint(bssid, active, ap_data))

    # Return AP list.
    return aps

  def _ParseScanAccessPoint(self, bssid, active, output):
    """Parses a particular AP in iw scan output into an AccessPoint object.

    Some of the logic in this function was derived from information here:
    https://wiki.archlinux.org/index.php/Wireless_network_configuration

    Args:
      bssid: BSSID of the access point in question.
      active: None if not associated to this AP.
      output: Output section from iw scan command for this particular AP.
        Should not include the first line showing the BSSID.

    Returns:
      An AccessPoint object representing the parsed access point.
    """
    logging.debug('BSSID %s data: %s', bssid, output)
    ap = AccessPoint()
    ap.bssid = bssid
    ap.active = active
    ap.ssid = ''  # Sometimes an AP doesn't have an SSID.
    ap.strength = None
    ap.quality = None
    encrypted = None

    for line in textwrap.dedent(output).splitlines():
      if ':' in line:
        key, _, value = [x.strip() for x in line.partition(':')]

        if key == 'SSID':
          ap.ssid = value

        elif key == 'signal':
          if 'dBm' in value:
            # Strength rating (dBm).
            ap.strength = float(value.partition(' dBm')[0])
          elif '/' in value:
            # Quality rating (out of 100).
            ap.quality = float(value.partition('/')[0])

        elif key == 'capability':
          encrypted = 'Privacy' in value

        elif key == 'WPA':
          ap.encryption_type = 'wpa'

        elif key == 'RSN':
          ap.encryption_type = 'wpa2'

        elif key == 'freq':
          ap.frequency = int(value)

        # The primary channel is located within the "HT operation" section.
        elif key.strip() == '* primary channel':
          ap.channel = int(value)

        elif key == 'last seen':
          matched = self._RE_LAST_SEEN.match(value)
          if matched:
            ap.last_seen = int(matched.group(1))

    # If no encryption type was encountered, but encryption is in place, the AP
    # uses WEP encryption.
    if encrypted and not ap.encryption_type:
      ap.encryption_type = 'wep'

    return ap

  def FindAccessPoint(self, ssid=None, frequency=None, active=None,
                      encrypted=None, interface=None,
                      scan_timeout=_SCAN_TIMEOUT_SECS):
    """Retrieves the first AccessPoint object with the given criteria.

    Args:
      ssid: the SSID of target access point. None to accept all SSIDs.
      active: a boolean indicating the target AP is currently associated or not.
          None to accept both cases.
      encrypted: a boolean indicating the target AP is encrypted or not. None to
          accept both cases.
      interface: the WiFi interface name used to connect APs. None to use the
          one retrieved from system.
      scan_timeout: timeout to find the target APs.

    Returns:
      the first AccessPoint object that match the criteria.

    Raises:
      WiFiError if no matching access point is found in scan_timeout seconds.
    """
    return self.FilterAccessPoints(
        interface=interface,
        ssid=ssid,
        frequency=frequency,
        active=active,
        encrypted=encrypted,
        scan_timeout=scan_timeout)[0]

  def FilterAccessPoints(self, ssid=None, frequency=None, active=None,
                         encrypted=None, interface=None,
                         scan_timeout=_SCAN_TIMEOUT_SECS):
    """Retrieves a list of AccessPoint objects matching criteria.

    Args:
      ssid: the SSID of target access point. None to accept all SSIDs.
      frequency: the frequency of target access point.
          None to accept all frequencies.
      active: a boolean indicating the target AP is currently associated or not.
          None to accept both cases.
      encrypted: a boolean indicating the target AP is encrypted or not. None to
          accept both cases.
      interface: the WiFi interface name used to connect APs. None to use the
          one retrieved from system.
      scan_timeout: timeout to find the target APs.

    Returns:
      a list of AccessPoint objects that match the criteria.

    Raises:
      WiFiError if no matching access point is found in scan_timeout seconds.
    """
    interface = self._ValidateInterface(interface)
    def _TryGetAccessPoints():
      # Filter frequency again because iw scan may report other frequency even
      # if frequency is specified in the command.
      return [ap for ap in self._AllAccessPoints(interface, frequency)
              if ((ssid is None or ssid == ap.ssid) and
                  (frequency is None or frequency == ap.frequency) and
                  (active is None or active == ap.active) and
                  (encrypted is None or encrypted == ap.encrypted))]

    # Grab output from the iw 'scan' command on the requested interface.  This
    # sometimes fails if the device is busy, and the AP might be unstable to
    # scan. So we may need to retry it a few times before getting output.
    try:
      return sync_utils.PollForCondition(
          poll_method=_TryGetAccessPoints,
          timeout_secs=scan_timeout,
          poll_interval_secs=0,
          condition_name='Attempting filter access points...')
    except type_utils.TimeoutError:
      raise WiFiError('No matching access points found')

  def Connect(self, ap, interface=None, passkey=None,
              connect_timeout=None, connect_attempt_timeout=None,
              dhcp_timeout=None):
    """Connects to a given AccessPoint.

    Returns:
      A connected Connection object.
    """
    if not isinstance(ap, AccessPoint):
      raise WiFiError('Expected AccessPoint for ap argument: %s' % ap)
    interface = self._ValidateInterface(interface)
    conn = self._NewConnection(
        dut=self._device, interface=interface,
        ap=ap, passkey=passkey,
        connect_timeout=connect_timeout,
        connect_attempt_timeout=connect_attempt_timeout,
        dhcp_timeout=dhcp_timeout,
        tmp_dir=self.tmp_dir)
    conn.Connect()
    return conn

  def FindAndConnectToAccessPoint(
      self, ssid=None, interface=None, passkey=None, scan_timeout=None,
      connect_timeout=None, dhcp_timeout=None, **kwargs):
    """Tries to find the given AccessPoint and connect to it.

    Returns:
      A connected Connection object.
    """
    interface = self._ValidateInterface(interface)
    ap = self.FindAccessPoint(ssid=ssid, interface=interface,
                              scan_timeout=scan_timeout, **kwargs)
    if not ap:
      raise WiFiError('Could not find AP with ssid=%s' % ssid)
    return self.Connect(ap, interface=interface, passkey=passkey,
                        connect_timeout=connect_timeout,
                        dhcp_timeout=dhcp_timeout)


class AccessPoint:
  """Represents a WiFi access point.

  Properties:
    ssid: SSID of AP (decoded into UTF-8 string).
    bssid: BSSID of AP (string with format 'xx:xx:xx:xx:xx:xx').
    channel: Channel of the AP (integer).
    frequency: Frequency of the AP (MHz as integer).
    active: Whether or not this network is currently associated.
    strength: Signal strength in dBm.
    quality: Link quality out of 100.
    encryption_type: Type of encryption used.  Can be one of:
      None, 'wep', 'wpa', 'wpa2'.
  """

  def __init__(self):
    self.ssid = None
    self.bssid = None
    self.channel = None
    self.frequency = None
    self.active = None
    self.strength = None
    self.quality = None
    self.encryption_type = None
    self.last_seen = None

  @property
  def encrypted(self):
    """Whether or not this AP is encrypted.

    False implies encryption_type == None.
    """
    return self.encryption_type is not None

  def __repr__(self):
    if not self.bssid:
      return 'AccessPoint()'
    strength = '{:.2f} dBm, '.format(
        self.strength) if self.strength is not None else ''
    quality = '{:.2f}/100, '.format(
        self.quality) if self.quality is not None else ''
    return (
        u'AccessPoint({ssid}, {bssid}, channel={channel}, '
        'frequency={frequency} MHz, {active}, '
        '{strength}{quality}encryption={encryption}, {last_seen}ms)'.format(
            ssid=self.ssid,
            bssid=self.bssid,
            channel=self.channel,
            frequency=self.frequency,
            active='active' if self.active else 'inactive',
            strength=strength,
            quality=quality,
            encryption=self.encryption_type or 'none',
            last_seen=self.last_seen)).encode('utf-8')


class WiFiAndroid(WiFi):
  """WiFi system module for Android systems."""
  def _NewConnection(self, *args, **kwargs):
    """See WiFi._NewConnection for details.

    Customizes DHCP method for Android devices.
    """
    kwargs.setdefault('dhcp_method', Connection.DHCP_DHCPCD)

    return Connection(*args, **kwargs)


class WiFiChromeOS(WiFi):
  """WiFi system module for Chrome OS systems."""

  _DHCLIENT_SCRIPT_PATH = '/usr/local/sbin/dhclient-script'

  def _NewConnection(self, *args, **kwargs):
    """Creates a new Connection object with the given arguments.

    Selects dhclient DHCP method for Chrome OS devices.
    Disables wpasupplicant when making a connection to an AP.
    """
    kwargs.setdefault('dhcp_method', Connection.DHCP_DHCLIENT)
    kwargs.setdefault('dhclient_script_path', self._DHCLIENT_SCRIPT_PATH)

    # Disables the wpasupplicant service, which seems to interfere with
    # the device during connection.  We make the assumption that wpasupplicant
    # will not be used by other parts of the factory test flow.
    # We add a sleep because it seems that if we continue bringing up the
    # WLAN interface directly afterwards, it has a change of being brought
    # right back down (either by wpasupplicant or something else).
    # TODO(kitching): Figure out a better way of either (a) disabling these
    # services temporarily, or (b) using Chrome OS's Shill to make the
    # connection.
    service = 'wpasupplicant'
    return_code = self._device.Call(['stop', service])
    if return_code == 0:
      logging.warning('Service %s does not stop before NewConnection. Add '
                      '"exclusive_resources": ["NETWORK"] to testlist if you '
                      'want to revive %s after test.', service, service)
      time.sleep(0.5)
    return Connection(*args, **kwargs)


class ConnectionStatus(type_utils.Obj):
  """A place holder for connection status.

  Attributes:
    signal: The current signal strength in type of
        `ConnectionStatus.Signal`.
    avg_signal: The average signal strength in type of
        `ConnectionStatus.Signal`.
    tx_bitrate: The bitrate of the TX channel.
    rx_bitrate: The bitrate of the RX channel.
  """
  class Signal(type_utils.Obj):
    def __init__(self, computed=None, antenna=None):
      """A place holder for RSSI signals.

      Attributes:
        computed: The signal strength the module sees/calculates.
        antenna: An array of the signal strengths of the antennas.
      """
      super(ConnectionStatus.Signal, self).__init__(computed=computed,
                                                    antenna=antenna)

  def __init__(
      self, signal=None, avg_signal=None, tx_bitrate=None, rx_bitrate=None):
    signal = signal or self.Signal()
    avg_signal = avg_signal or self.Signal()
    super(ConnectionStatus, self).__init__(
        signal=signal, avg_signal=avg_signal, tx_bitrate=tx_bitrate,
        rx_bitrate=rx_bitrate)


class Connection:
  """Represents a connection to a particular AccessPoint."""
  DHCP_DHCPCD = 'dhcpcd'
  DHCP_DHCLIENT = 'dhclient'
  _CONNECT_TIMEOUT = 20
  _CONNECT_ATTEMPT_TIMEOUT = 10
  _DHCP_TIMEOUT = 10

  _CONN_STATUS_SIGNALS_RE = re.compile(r'^\s*signal:.*$')
  _CONN_STATUS_AVG_SIGNALS_RE = re.compile(r'^\s*signal avg:.*$')
  _CONN_STATUS_TX_BITRATE_RE = re.compile(r'^\s*tx bitrate:.*$')
  _CONN_STATUS_RX_BITRATE_RE = re.compile(r'^\s*rx bitrate:.*$')

  def __init__(self, dut, interface, ap, passkey,
               connect_timeout=None, connect_attempt_timeout=None,
               dhcp_timeout=None,
               tmp_dir=None, dhcp_method=DHCP_DHCLIENT,
               dhclient_script_path=None):
    self._device = dut
    self.interface = interface
    self.ap = ap
    self.passkey = passkey

    # IP can be queried after connecting.
    self.ip = None

    self._auth_process = None
    self._dhcp_process = None
    self._connect_timeout = (self._CONNECT_TIMEOUT if connect_timeout is None
                             else connect_timeout)
    self._connect_attempt_timeout = (
        self._CONNECT_ATTEMPT_TIMEOUT if connect_attempt_timeout is None
        else connect_attempt_timeout)
    self._dhcp_timeout = (self._DHCP_TIMEOUT if dhcp_timeout is None
                          else dhcp_timeout)
    self._tmp_dir = None
    self._tmp_dir_handle = None
    self._user_tmp_dir = tmp_dir
    if dhcp_method == self.DHCP_DHCPCD:
      self._dhcp_fn = self._RunDHCPCD
    else:
      self._dhcp_fn = self._RunDHCPClient

    # Arguments for DHCP function.
    self._dhcp_args = {'dhclient_script_path': dhclient_script_path}

  def _DisconnectAP(self):
    """Disconnects from the current AP."""
    disconnect_command = 'iw dev {interface} disconnect'.format(
        interface=self.interface)
    # This call may fail if we are not connected to any network.
    self._device.Call(disconnect_command)

  def _Connect(self, connect_fn=None):
    """Retries the given function to connect to the AP."""
    connect_fn = connect_fn or (lambda: True)
    def AttemptConnect():
      # Scan first, and then connect directly afterwards.  We do this because
      # some buggy drivers require the scan and connect steps to be in rapid
      # succession for a connect to work properly.
      logging.info('Scanning...')
      self._device.Call(['iw', 'dev', self.interface, 'scan'])
      logging.info('Running connect_fn...')
      connect_fn()
      logging.info('Checking for connection...')
      return self._WaitConnect()
    return sync_utils.WaitFor(AttemptConnect, self._connect_timeout)

  def _WaitConnect(self):
    """Blocks until authenticated and connected to the AP."""
    CHECK_SUCCESS_PREFIX = 'Connected to'
    check_command = 'iw dev {interface} link'.format(interface=self.interface)
    logging.info('Waiting to connect to AP...')
    def CheckConnected():
      return self._device.CheckOutput(
          check_command).startswith(CHECK_SUCCESS_PREFIX)
    try:
      return sync_utils.WaitFor(CheckConnected, self._connect_attempt_timeout)
    except type_utils.TimeoutError:
      return False

  def Connect(self):
    """Connects to the AP."""
    if self.ap.encrypted and not self.passkey:
      raise WiFiError('Require passkey to connect to encrypted network')
    self._DisconnectAP()

    # Create temporary directory.
    if self._user_tmp_dir:
      self._tmp_dir = self._user_tmp_dir
    else:
      self._tmp_dir_handle = self._device.temp.TempDirectory()
      self._tmp_dir = self._tmp_dir_handle.__enter__()

    # First, bring the device up.  If it is already up, this will succeed
    # anyways.
    logging.debug('Bringing up ifconfig...')
    self._device.CheckCall(['ifconfig', self.interface, 'up'])

    # Authenticate to the server.
    auth_fns = {
        'wep': self._AuthenticateWEP,
        'wpa': self._AuthenticateWPA,
        'wpa2': self._AuthenticateWPA}
    auth_process = auth_fns.get(
        self.ap.encryption_type, self._AuthenticateOpen)()
    next(auth_process)

    # Grab an IP address.
    dhcp_process = self._dhcp_fn(**self._dhcp_args)
    self.ip = next(dhcp_process)

    # Store for disconnection.
    self._auth_process = auth_process
    self._dhcp_process = dhcp_process

  def Disconnect(self):
    """Disconnects from the AP."""
    if not self._auth_process or not self._dhcp_process:
      raise WiFiError('Must connect before disconnecting')

    self.ip = None
    dhcp_process, self._dhcp_process = self._dhcp_process, None
    auth_process, self._auth_process = self._auth_process, None
    next(dhcp_process)
    next(auth_process)

    # Remove temporary directory.
    if not self._user_tmp_dir:
      self._tmp_dir_handle.__exit__(None, None, None)
      self._tmp_dir = None

  def GetStatus(self):
    def _ParseSignal(s):
      try:
        # the command output must looks like "  signal: -50 [-40 -60] dBm"
        data = s.partition(':')[2].strip()
        assert data.endswith('] dBm')
        data = data[:-5].replace(' ', '')
        computed, unused_sep, antenna = data.partition('[')
        return ConnectionStatus.Signal(
            int(computed), [int(a) for a in antenna.split(',')])
      except Exception as e:
        raise WiFiError('unexpected signal format: %r, %r' % (s, e))

    def _ParseBitRate(s):
      try:
        # the command output must looks like "  tx bitrate: 400 MBit/s bla bla"
        words = s.partition(':')[2].strip().split(' ')
        assert words[1] == 'MBit/s'
        return float(words[0])
      except Exception as e:
        raise WiFiError('unexpected tx_bitrate format: %r, %r' % (s, e))

    try:
      out = self._device.CheckOutput(['iw', self.interface, 'station', 'dump'])
    except device_types.CalledProcessError as e:
      raise WiFiError('unable to fetch the connection status: %r' % e)

    ret = ConnectionStatus()
    cases = [('signal', _ParseSignal, self._CONN_STATUS_SIGNALS_RE),
             ('avg_signal', _ParseSignal, self._CONN_STATUS_AVG_SIGNALS_RE),
             ('tx_bitrate', _ParseBitRate, self._CONN_STATUS_TX_BITRATE_RE),
             ('rx_bitrate', _ParseBitRate, self._CONN_STATUS_RX_BITRATE_RE)]
    for line in out.splitlines():
      for attr_name, parse_func, regexp in cases:
        if regexp.match(line):
          setattr(ret, attr_name, parse_func(line))
          break

    return ret

  def _LeasedIP(self):
    """Returns current leased IP.

    Returns:
      Leased IP as a string or False if not yet leased.
    """
    check_command = 'ip addr show {interface} | grep "inet "'.format(
        interface=self.interface)
    try:
      # grep exit with return code 0 when we have retrieved an IP.
      out = self._device.CheckOutput(check_command)
    except device_types.CalledProcessError:
      return False
    # ex: inet 192.168.159.78/20 brd 192.168.159.255 scope global wlan0
    return out.split()[1].split('/')[0]

  def _RunDHCPCD(self, **kwargs):
    """Grabs an IP for the device using the dhcpcd command."""
    del kwargs
    clear_ifconfig_command = 'ifconfig {interface} 0.0.0.0'.format(
        interface=self.interface)
    # -K: Don't receive link messages for carrier status.  You should
    #     only have to use this with buggy device drivers or running
    #     dhcpcd through a network manager.
    # -c: Location to the hooks file.  If the default location happens to be
    #     empty, dhcpcd will fail.  So we set the hooks file to /dev/null.
    dhcp_command = ('dhcpcd -K -t {timeout} -c /dev/null {interface}').format(
        timeout=self._dhcp_timeout,
        interface=self.interface)
    dhcp_timeout_command = 'timeout {timeout} {cmd}'.format(
        timeout=self._dhcp_timeout,
        cmd=dhcp_command)
    force_kill_command = 'pgrep dhcpcd | xargs -r kill -9'

    logging.info('Killing any existing dhcpcd processes...')
    self._device.Call(force_kill_command)

    logging.info('Clearing any existing ifconfig networks...')
    self._device.Call(clear_ifconfig_command)

    logging.info('Starting dhcpcd...')
    self._device.CheckCall(dhcp_timeout_command)

    logging.info('Verifying IP address...')
    ip = self._LeasedIP()
    if not ip:
      self._device.Call(force_kill_command)
      raise WiFiError('DHCP bind failed')
    logging.info('Success: bound to IP %s', ip)

    yield ip  # We have bound an IP; yield back to the caller.

    logging.info('Killing any remaining dhcpcd processes...')
    self._device.Call(force_kill_command)

    yield  # We have released the IP.

  def _RunDHCPClient(self, dhclient_script_path=None, **kwargs):
    """Grabs an IP for the device using the dhclient command."""
    del kwargs
    PID_FILE = os.path.join(self._tmp_dir, 'dhclient.pid')
    clear_ifconfig_command = 'ifconfig {interface} 0.0.0.0'.format(
        interface=self.interface)
    dhcp_command = ('echo "" | '  # dhclient expects STDIN for some reason
                    'dhclient -4 '  # only run on IPv4
                    '-nw '  # immediately daemonize
                    '-pf {pid_file} '
                    '-sf {dhclient_script} '
                    '-lf /dev/null '  # don't keep a leases file
                    '-v {interface}'.format(
                        pid_file=PID_FILE,
                        dhclient_script=dhclient_script_path,
                        interface=self.interface))
    kill_command = 'cat {pid_file} | xargs -r kill; rm {pid_file}'.format(
        pid_file=PID_FILE)
    force_kill_command = 'pgrep dhclient | xargs -r kill -9'

    logging.info('Killing any existing dhclient processes...')
    self._device.Call(force_kill_command)

    logging.info('Clearing any existing ifconfig networks...')
    self._device.Call(clear_ifconfig_command)

    logging.info('Starting dhclient...')
    self._device.CheckCall(dhcp_command)

    logging.info('Waiting to lease an IP...')
    ip = sync_utils.WaitFor(self._LeasedIP, self._dhcp_timeout)
    if not ip:
      self._device.Call(kill_command)
      raise WiFiError('DHCP bind failed')
    logging.info('Success: bound to IP %s', ip)

    yield ip  # We have bound an IP; yield back to the caller.

    logging.info('Stopping dhclient...')
    self._device.Call(kill_command)
    self._device.Call(force_kill_command)
    self._device.Call(clear_ifconfig_command)

    yield  # We have released the IP.

  def _AuthenticateOpen(self):
    """Connects to an open network."""
    # TODO(kitching): Escape quotes in ssid properly.
    if self.ap.frequency is None:
      connect_command = u'iw dev {interface} connect {ssid}'.format(
          interface=self.interface,
          ssid=self.ap.ssid)
    else:
      connect_command = u'iw dev {interface} connect {ssid} {freq}'.format(
          interface=self.interface,
          ssid=self.ap.ssid,
          freq=self.ap.frequency)

    # Pause until connected.  Throws exception if failed.
    def ConnectOpen():
      logging.info('Connecting to open network...')
      self._device.CheckCall(connect_command)
    if not self._Connect(ConnectOpen):
      raise WiFiError('Connection to open network failed')

    yield  # We are connected; yield back to the caller.

    logging.info('Disconnecting from open network...')
    self._DisconnectAP()

    yield  # We have disconnected.

  def _AuthenticateWEP(self):
    """Authenticates and connect to a WEP network."""
    # TODO(kitching): Escape quotes in ssid and passkey properly.
    if self.ap.frequency is None:
      connect_command = (
          u'iw dev {interface} connect {ssid} key 0:{passkey}'.format(
              interface=self.interface,
              ssid=self.ap.ssid,
              passkey=self.passkey))
    else:
      connect_command = (
          u'iw dev {interface} connect {ssid} {freq} key 0:{passkey}'.format(
              interface=self.interface,
              ssid=self.ap.ssid,
              freq=self.ap.frequency,
              passkey=self.passkey))

    # Pause until connected.  Throws exception if failed.
    def ConnectWEP():
      logging.info('Connecting to WEP network...')
      self._device.CheckCall(connect_command)
    if not self._Connect(ConnectWEP):
      raise WiFiError('Connection to WEP network failed')

    yield  # We are connected; yield back to the caller.

    logging.info('Disconnecting from WEP network...')
    self._DisconnectAP()

    yield  # We have disconnected.

  def _AuthenticateWPA(self):
    """Authenticates and connect to a WPA network."""
    if self.passkey is None:
      raise WiFiError('Passkey is needed for WPA/WPA2 authentication')

    PID_FILE = os.path.join(self._tmp_dir, 'wpa_supplicant.pid')
    WPA_FILE = os.path.join(self._tmp_dir, 'wpa.conf')
    # TODO(kitching): Escape quotes in ssid and passkey properly.
    wpa_passphrase_command = (
        u'wpa_passphrase {ssid} {passkey} > {wpa_file}'.format(
            ssid=self.ap.ssid,
            passkey=self.passkey,
            wpa_file=WPA_FILE))
    wpa_supplicant_command = (
        'wpa_supplicant '
        '-B '  # daemonize
        '-P {pid_file} '
        '-D nl80211 '
        '-i {interface} '
        '-c {wpa_file}'.format(
            pid_file=PID_FILE,
            interface=self.interface,
            wpa_file=WPA_FILE))
    kill_command = (
        'cat {pid_file} | xargs -r kill; '
        'rm {pid_file}; rm {wpa_file}'.format(
            pid_file=PID_FILE,
            wpa_file=WPA_FILE))
    force_kill_command = 'killall wpa_supplicant'

    logging.info('Killing any existing wpa_command processes...')
    self._device.Call(force_kill_command)

    logging.info('Creating wpa.conf...')
    self._device.CheckCall(wpa_passphrase_command)

    logging.info('Launching wpa_supplicant...')
    self._device.CheckCall(wpa_supplicant_command)

    # Pause until connected.  Throws exception if failed.
    if not self._Connect():
      self._device.Call(kill_command)
      raise WiFiError('Connection to WPA network failed')

    yield  # We are connected; yield back to the caller.

    logging.info('Stopping wpa_supplicant...')
    self._device.Call(kill_command)
    self._device.Call(force_kill_command)

    logging.info('Disconnecting from WPA network...')
    self._DisconnectAP()

    yield  # We have disconnected.

class ServiceSpec(type_utils.Obj):
  def __init__(self, ssid, freq, password):
    super(ServiceSpec, self).__init__(ssid=ssid, freq=freq, password=password)

  def __hash__(self):
    return hash((self.ssid, self.freq, self.password))

class WiFiChip:
  """WiFiChip is an abstaction of a signal data collection."""

  def __init__(self, device, interface, phy_name):
    self._device = device
    self._interface = interface
    self._phy_name = phy_name

  def ScanSignal(self, service, antenna, scan_count):
    """Collects strength of signals.

    This may collect multiple signal at the same time.

    For example, "iw scan" with frequency specified can collect all signals from
    that frequency. Another example is by decoding radiotap packages and get
    signals of all antennas of an access point at once.

    Attributes:
      service: The service object, which contains information to identify an AP.
      antenna: The antenna that used to scan.
      scan_count: An integer. Number of scans to get average signal strength.
    """
    raise NotImplementedError

  def GetAverageSignal(self, service, antenna):
    """Get the average signal strength of (service, antenna)."""
    raise NotImplementedError

  def Destroy(self):
    """Restore wifi to initial state."""
    raise NotImplementedError
