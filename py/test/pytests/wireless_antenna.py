# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for basic Wifi.

Description
-----------
This test checks if the signal strength of the antennas satisfy the input spec.

This test can accept a list of wireless services but only the strongest one is
used as the test AP and the other APs are ignored.

This test can test signal strength via ``iw dev {device} scan`` or radiotap.

Be sure to set AP correctly.
1. Select a fixed channel instead of auto.
2. Disable the power control in AP.
3. Make sure SSID of AP is unique.

Test Procedure
--------------
1. Accepts a dict of antenna:strength and a list of (ssid, frequency).
2. For each (antenna, AP=(ssid, frequency)), we test the signal strength of it.
3. Chooses AP with maximum strength as the test AP.
4. Checks if (antenna, test AP) is greater than the spec for all antennas.

Dependency
----------
- `iw` utility
- `ifconfig` utility
- `ip` utility (radiotap)
- `tcpdump` utility (radiotap)
- ``iw phy {phy_name} set antenna 1 1`` (switch_antenna)

Examples
--------
To run this test on DUT, add a test item in the test list::

  {
    "pytest_name": "wireless_antenna",
    "args": {
      "device_name": "wlan0",
      "services": [
        ["my_ap_service", 5745, null]
      ],
      "strength": {
        "main": -60,
        "aux": -60,
        "all": -60
      },
      "scan_count": 10,
      "switch_antenna_sleep_secs": 1
    }
  }
"""

import collections
import logging
import re
import struct
import subprocess
import sys

from cros.factory.device import device_types
from cros.factory.device import device_utils
from cros.factory.device import wifi
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils import type_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.schema import JSONSchemaDict

_ARG_SERVICES_SCHEMA = JSONSchemaDict('services schema object', {
    'type': 'array',
    'items': {
        'type': 'array',
        'items': [
            {'type': 'string'},
            {'type': ['integer', 'null']},
            {'type': ['string', 'null']}
        ],
        'minItems': 3,
        'maxItems': 3
    }
})
_ARG_SWITCH_ANTENNA_CONFIG_SCHEMA = JSONSchemaDict(
    'switch antenna config schema object',
    {
        'type': 'object',
        'properties': {
            'main': {
                'type': 'array',
                'items': {'type': 'integer'},
                'minItems': 2,
                'maxItems': 2
            },
            'aux': {
                'type': 'array',
                'items': {'type': 'integer'},
                'minItems': 2,
                'maxItems': 2
            },
            'all': {
                'type': 'array',
                'items': {'type': 'integer'},
                'minItems': 2,
                'maxItems': 2
            },
        },
        'additionalProperties': False,
        'required': ['main', 'aux', 'all']
    })
_ARG_STRENGTH_SCHEMA = JSONSchemaDict('strength schema object', {
    'type': 'object',
    'additionalProperties': {'type': 'number'}
})

_DEFAULT_SWITCH_ANTENNA_CONFIG = {'main': [1, 1],
                                  'aux': [2, 2],
                                  'all': [3, 3]}


class SwitchAntennaWiFiChip(wifi.WiFiChip):

  # The scanned result with last_seen value greater than this value
  # will be ignored.
  _THRESHOLD_LAST_SEEN_MS = 1000

  def __init__(self, device, interface, phy_name, services,
               switch_antenna_config, switch_antenna_sleep_secs, scan_timeout):
    super(SwitchAntennaWiFiChip, self).__init__(device, interface, phy_name)
    self._services = [(service.ssid, service.freq) for service in services]
    self._switch_antenna_config = switch_antenna_config
    self._signal_table = {antenna: {service: []
                                    for service in self._services}
                          for antenna in self._switch_antenna_config}
    self._antenna = None
    self._switch_antenna_sleep_secs = switch_antenna_sleep_secs
    self._scan_timeout = scan_timeout

  def ScanSignal(self, service, antenna, scan_count):
    service_index = (service.ssid, service.freq)
    for unused_try_count in range(scan_count):
      if len(self._signal_table[antenna][service_index]) >= scan_count:
        break
      self.SwitchAntenna(antenna)
      scan_output = self._device.wifi.FilterAccessPoints(
          interface=self._interface, frequency=service.freq,
          scan_timeout=self._scan_timeout)

      same_freq_service = {s: []
                           for s in self._services if s[1] == service.freq}
      for ap in scan_output:
        scanned_service = (ap.ssid, ap.frequency)
        if (ap.last_seen <= self._THRESHOLD_LAST_SEEN_MS and
            scanned_service in same_freq_service):
          same_freq_service[scanned_service].append(ap)

      for scanned_service, duplicates in same_freq_service.items():
        if not duplicates:
          session.console.warning(
              'Can not scan service %s %d.',
              scanned_service[0], scanned_service[1])
          continue
        if len(duplicates) > 1:
          session.console.warning(
              'There are more than one result for service %s %d.',
              scanned_service[0], scanned_service[1])
          for ap in duplicates:
            session.console.warning(
                'mac: %s, ssid: %s, freq: %d, signal %f, last_seen %d ms',
                ap.bssid, ap.ssid, ap.frequency, ap.strength, ap.last_seen)
        # Use the one with strongest signal if duplicates.
        ap = max(duplicates, key=lambda t: t.strength)
        session.console.info(
            'scan : %s %s %d %f %d ms.', ap.ssid, ap.bssid, ap.frequency,
            ap.strength, ap.last_seen)
        self._signal_table[antenna][scanned_service].append(ap.strength)

  def GetAverageSignal(self, service, antenna):
    """Get the average signal strength of (service, antenna)."""
    result = self._signal_table[antenna][(service.ssid, service.freq)]
    return sum(result) / len(result) if result else None

  def Destroy(self):
    """Restores antenna config to 'all' if it is not 'all'."""
    if self._antenna == 'all':
      logging.info('Already using antenna "all".')
    else:
      logging.info('Restore antenna.')
      self.SwitchAntenna('all')

  def SwitchAntenna(self, antenna, max_retries=10):
    """Sets antenna using iw command.

    Args:
      max_retries: The maximum retry time to set antenna.
      switch_antenna_sleep_secs: The sleep time after switching antenna and
          ifconfig up.

    Raises:
      WiFiError if fail to set antenna for max_retries tries.
    """
    if self._antenna == antenna:
      return
    tx_bitmap, rx_bitmap = self._switch_antenna_config[antenna]
    self._device.wifi.BringsDownInterface(self._interface)
    try_count = 0
    success = False
    while try_count < max_retries:
      process = self._device.Popen(
          ['iw', 'phy', self._phy_name, 'set', 'antenna', str(tx_bitmap),
           str(rx_bitmap)],
          stdout=subprocess.PIPE, stderr=subprocess.PIPE, log=True)
      unused_stdout, stderr = process.communicate()
      retcode = process.returncode
      if retcode == 0:
        success = True
        break
      # (-95) EOPNOTSUPP Operation not supported on transport endpoint
      # Do ifconfig down again may solve this problem.
      if retcode == 161:
        try_count += 1
        logging.info('Retry...')
        self._device.wifi.BringsDownInterface(self._interface)
      else:
        raise wifi.WiFiError('Failed to set antenna. ret code: %d. stderr: %s' %
                             (retcode, stderr))
    self._device.wifi.BringsUpInterface(self._interface,
                                        self._switch_antenna_sleep_secs)
    if not success:
      raise wifi.WiFiError('Failed to set antenna for %s tries' % max_retries)
    self._antenna = antenna


class DisableSwitchWiFiChip(SwitchAntennaWiFiChip):

  def SwitchAntenna(self, antenna, unused_max_retries=10):
    if self._antenna == antenna:
      return
    logging.info('Switching antenna is disabled. Skipping setting antenna to'
                 ' %s. Just bring up the interface.', antenna)
    # Bring up the interface because IwSetAntenna brings up interface after
    # antenna is switched.
    self._device.wifi.BringsUpInterface(self._interface,
                                        self._switch_antenna_sleep_secs)
    self._antenna = antenna


_RE_BEACON = re.compile(r'(\d+) MHz.*Beacon \((.+)\)')


class RadiotapPacket:
  FIELD = collections.namedtuple('Field', ['name', 'struct', 'align'])
  ANTENNA_SIGNAL_FIELD = FIELD('Antenna Signal', struct.Struct('b'), 0)
  ANTENNA_INDEX_FIELD = FIELD('Antenna Index', struct.Struct('B'), 0)
  EXTENDED_BIT = 31
  FIELDS = [
      FIELD('TSFT', struct.Struct('Q'), 8),
      FIELD('Flags', struct.Struct('B'), 0),
      FIELD('Rate', struct.Struct('B'), 0),
      FIELD('Channel', struct.Struct('HH'), 2),
      FIELD('FHSS', struct.Struct('BB'), 0),
      ANTENNA_SIGNAL_FIELD,
      FIELD('Antenna Noise', struct.Struct('b'), 0),
      FIELD('Lock Quality', struct.Struct('H'), 2),
      FIELD('TX Attenuation', struct.Struct('H'), 2),
      FIELD('dB TX Attenuation', struct.Struct('H'), 2),
      FIELD('dBm TX Power', struct.Struct('b'), 1),
      ANTENNA_INDEX_FIELD,
      FIELD('dB Antenna Signal', struct.Struct('B'), 0),
      FIELD('dB Antenna Noise', struct.Struct('B'), 0),
      FIELD('RX Flags', struct.Struct('H'), 2),
      FIELD('TX Flags', struct.Struct('H'), 2),
      FIELD('RTS Retries', struct.Struct('B'), 0),
      FIELD('Data Retries', struct.Struct('B'), 0),
      None,
      FIELD('MCS', struct.Struct('BBB'), 1),
      FIELD('AMPDU status', struct.Struct('IHBB'), 4),
      FIELD('VHT', struct.Struct('HBBBBBBBBH'), 2),
      FIELD('Timestamp', struct.Struct('QHBB'), 8),
      None,
      None,
      None,
      None,
      None,
      None]
  MAIN_HEADER_FORMAT = struct.Struct('BBhI')
  PARSE_INFO = collections.namedtuple('AntennaData', ['header_size',
                                                      'data_bytes',
                                                      'antenna_offsets'])

  # This is a variable-length header, but this is what we want to see.
  EXPECTED_HEADER_FORMAT = struct.Struct(MAIN_HEADER_FORMAT.format + b'II')

  @staticmethod
  def Decode(packet_bytes):
    """Returns signal strength data for each antenna.

    Format is {all_signal, {antenna_index, antenna_signal}}.
    """
    if len(packet_bytes) < RadiotapPacket.EXPECTED_HEADER_FORMAT.size:
      return None
    parts = RadiotapPacket.EXPECTED_HEADER_FORMAT.unpack_from(packet_bytes)
    present0, present1, present2 = parts[3:]
    parse_info = RadiotapPacket.ParseHeader([present0, present1, present2])
    required_bytes = parse_info.header_size + parse_info.data_bytes
    if len(packet_bytes) < required_bytes:
      return None
    antenna_data = []
    for datum in filter(bool, parse_info.antenna_offsets):
      signal = datum.get(RadiotapPacket.ANTENNA_SIGNAL_FIELD)
      if RadiotapPacket.ANTENNA_SIGNAL_FIELD not in datum:
        continue
      signal_offset = datum[RadiotapPacket.ANTENNA_SIGNAL_FIELD]
      signal, = RadiotapPacket.ANTENNA_SIGNAL_FIELD.struct.unpack_from(
          packet_bytes[(signal_offset + parse_info.header_size):])
      if RadiotapPacket.ANTENNA_INDEX_FIELD in datum:
        index_offset = datum[RadiotapPacket.ANTENNA_INDEX_FIELD]
        index, = RadiotapPacket.ANTENNA_SIGNAL_FIELD.struct.unpack_from(
            packet_bytes[(index_offset + parse_info.header_size):])
        antenna_data.append((index, signal))
      else:
        antenna_data.append(signal)
    return antenna_data

  @staticmethod
  def ParseHeader(field_list):
    """Returns packet information of the radiotap header should have."""
    header_size = RadiotapPacket.MAIN_HEADER_FORMAT.size
    data_bytes = 0
    antenna_offsets = []

    for bitmask in field_list:
      antenna_offsets.append({})
      for bit, field in enumerate(RadiotapPacket.FIELDS):
        if bitmask & (1 << bit):
          if field is None:
            session.console.warning(
                'Unknown field at bit %d is given in radiotap packet, the '
                'result would probably be wrong...')
            continue
          if field.align and (data_bytes % field.align):
            data_bytes += field.align - (data_bytes % field.align)
          if field in (RadiotapPacket.ANTENNA_SIGNAL_FIELD,
                       RadiotapPacket.ANTENNA_INDEX_FIELD):
            antenna_offsets[-1][field] = data_bytes
          data_bytes += field.struct.size

      if not bitmask & (1 << RadiotapPacket.EXTENDED_BIT):
        break
      header_size += 4
    else:
      raise NotImplementedError('Packet has too many extensions for me!')

    # Offset the antenna fields by the header size.
    return RadiotapPacket.PARSE_INFO(header_size, data_bytes, antenna_offsets)


class Capture:
  """Context for a live tcpdump packet capture for beacons."""

  def __init__(self, dut: device_types.DeviceBoard, device_name, phy,
               keep_monitor):
    self.dut = dut
    self.monitor_process = None
    self.created_device = None
    self.parent_device = device_name
    self.phy = phy
    self.keep_monitor = keep_monitor

  def CreateDevice(self, monitor_device='antmon0'):
    """Creates a monitor device to monitor beacon."""
    # This command returns 0 if the monitor_device exists.
    return_value = self.dut.Call(['iw', 'dev', monitor_device, 'info'],
                                 log=True)
    if return_value == 0:
      self.created_device = monitor_device
      if self.keep_monitor:
        return
      # The device may exist if the test is aborted after CreateDevice and
      # before RemoveDevice. We remove it here to make sure we use a new
      # monitor.
      self.RemoveDevice()

    # This command creates the monitor_device.
    self.dut.CheckCall(['iw', self.parent_device, 'interface', 'add',
                        monitor_device, 'type', 'monitor'], log=True)
    self.created_device = monitor_device

  def RemoveDevice(self):
    """Removes the monitor device."""
    if self.created_device is None:
      return
    if not self.keep_monitor:
      # This command removes the monitor_device.
      self.dut.CheckCall(['iw', self.created_device, 'del'], log=True)
    self.created_device = None

  def GetSignal(self):
    """Gets signal from tcpdump."""
    while True:
      line = self.monitor_process.stdout.readline()
      m = _RE_BEACON.search(line)
      if m:
        freq = int(m.group(1))
        ssid = m.group(2)
        break
    packet_bytes = b''
    while True:
      line = self.monitor_process.stdout.readline()
      if not line.startswith('\t0x'):
        break

      # Break up lines of the form "\t0x0000: abcd ef" into a bytes
      # b"\xab\xcd\xef".
      parts = line[3:].split()
      for part in parts[1:]:
        packet_bytes += bytes((int(part[:2], 16),))
        if len(part) > 2:
          packet_bytes += bytes((int(part[2:], 16),))
      packet = RadiotapPacket.Decode(packet_bytes)
      if packet:
        return {'ssid': ssid, 'freq': freq, 'signal': packet}

  def set_beacon_filter(self, value):
    """Sets beacon filter.

    This function is currently only needed for Intel WiFi.
    """
    path = '/sys/kernel/debug/ieee80211/%s/netdev:%s/iwlmvm/bf_params' % (
        self.phy, self.parent_device)
    if self.dut.path.exists(path):
      session.console.info('Setting beacon filter (enable=%d) for Intel WiFi',
                           value)
      self.dut.WriteFile(path, 'bf_enable_beacon_filter=%d\n' % value)

  def Create(self):
    if not self.created_device:
      self.CreateDevice()
    self.dut.CheckCall(
        ['ip', 'link', 'set', self.created_device, 'up'], log=True)
    self.dut.CheckCall(
        ['iw', self.parent_device, 'set', 'power_save', 'off'], log=True)
    self.set_beacon_filter(0)
    self.monitor_process = self.dut.Popen(
        ['tcpdump', '-nUxxi', self.created_device, 'type', 'mgt',
         'subtype', 'beacon'], stdout=subprocess.PIPE, log=True)

  def Destroy(self):
    if self.monitor_process:
      self.monitor_process.kill()
      self.monitor_process.wait()
      self.monitor_process = None
    self.set_beacon_filter(1)
    self.RemoveDevice()


class RadiotapWiFiChip(wifi.WiFiChip):

  _ANTENNA_CONFIG = ['all', 'main', 'aux']

  def __init__(self, device, interface, phy_name, services, connect_timeout,
               scan_timeout, keep_monitor):
    super(RadiotapWiFiChip, self).__init__(device, interface, phy_name)
    self._services = [(service.ssid, service.freq) for service in services]
    self._signal_table = {service: {antenna: []
                                    for antenna in self._ANTENNA_CONFIG}
                          for service in self._services}
    self._ap = None
    self._connection = None
    self._connect_timeout = connect_timeout
    self._scan_timeout = scan_timeout
    self._keep_monitor = keep_monitor

  def ScanSignal(self, service, antenna, scan_count):
    target_service = (service.ssid, service.freq)
    capture_times = len(self._signal_table[target_service][antenna])
    if capture_times >= scan_count:
      return

    session.console.info('Switching to AP %s %d...' % target_service)
    if not self._ConnectService(service.ssid, service.password,
                                freqs=service.freq):
      return

    capture = Capture(self._device, self._interface, self._phy_name,
                      self._keep_monitor)
    try:
      capture.Create()
      while capture_times < scan_count:
        signal_result = capture.GetSignal()
        if (signal_result['ssid'] == service.ssid and
            signal_result['freq'] == service.freq):
          session.console.info('%s', signal_result)
          signal = signal_result['signal']
          self._signal_table[target_service]['all'].append(signal[0])
          self._signal_table[target_service]['main'].append(signal[1][1])
          self._signal_table[target_service]['aux'].append(signal[2][1])
          capture_times += 1
        else:
          session.console.info('Ignore the signal %r', signal_result)
    finally:
      capture.Destroy()

    self._DisconnectService()

  def GetAverageSignal(self, service, antenna):
    """Get the average signal strength of (service, antenna)."""
    result = self._signal_table[(service.ssid, service.freq)][antenna]
    return sum(result) / len(result) if result else None

  def Destroy(self):
    self._DisconnectService()

  def _ConnectService(self, service_name, password, freqs):
    """Associates a specified wifi AP.

    Password can be '' or None.
    """
    try:
      self._ap = self._device.wifi.FindAccessPoint(
          ssid=service_name, interface=self._interface, frequency=freqs,
          scan_timeout=self._scan_timeout)
    except wifi.WiFiError as e:
      session.console.info(
          'Unable to find the service %s: %r' % (service_name, e))
      return False

    try:
      self._connection = self._device.wifi.Connect(
          self._ap, interface=self._interface, passkey=password,
          connect_timeout=self._connect_timeout)
    except type_utils.TimeoutError as e:
      session.console.info('Unable to connect to the service %s' % service_name)
      return False

    session.console.info(
        'Successfully connected to service %s', service_name)
    return True

  def _DisconnectService(self):
    """Disconnect wifi AP."""
    if self._connection:
      self._connection.Disconnect()
      session.console.info('Disconnect to service %s', self._ap.ssid)
      self._connection = None


class WirelessTest(test_case.TestCase):
  """Basic wireless test class.

  Properties:
    _phy_name: wireless phy name to test.
  """
  ARGS = [
      Arg('device_name', str,
          ('Wireless device name to test. e.g. wlan0. If not specified, it will'
           'fail if multiple devices are found, otherwise use the only one '
           'device it found.'), default=None),
      Arg('services', list, (
          'A list of ``[<service_ssid>:str, <freq>:int|None, '
          '<password>:str|None]`` sequences like ``[[SSID1, FREQ1, PASS1], '
          '[SSID2, FREQ2, PASS2], ...]``. Each sequence should contain '
          'exactly 3 items. If ``<freq>`` is ``None`` the test '
          'will detect the frequency by ``iw <device_name> scan`` command '
          'automatically.  ``<password>=None`` implies the service can connect '
          'without a password.'), schema=_ARG_SERVICES_SCHEMA),
      Arg('ignore_missing_services', bool,
          ('Ignore services that are not found during scanning. This argument '
           'is not needed for switch antenna wifi chip'), default=False),
      Arg('scan_timeout', int, 'Timeout for scanning the services.',
          default=20),
      Arg('connect_timeout', int, 'Timeout for connecting to the service.',
          default=10),
      Arg('strength', dict,
          ('A dict of minimal signal strengths. For example, a dict like '
           '``{"main": strength_1, "aux": strength_2, "all": strength_all}``. '
           'The test will check signal strength according to the different '
           'antenna configurations in this dict.'),
          schema=_ARG_STRENGTH_SCHEMA),
      Arg('scan_count', int, 'Number of scans to get average signal strength.',
          default=5),
      Arg('switch_antenna_config', dict,
          ('A dict of ``{"main": (tx, rx), "aux": (tx, rx), "all": (tx, rx)}`` '
           'for the config when switching the antenna.'),
          default=_DEFAULT_SWITCH_ANTENNA_CONFIG,
          schema=_ARG_SWITCH_ANTENNA_CONFIG_SCHEMA),
      Arg('switch_antenna_sleep_secs', int,
          ('The sleep time after switching antenna and ifconfig up. Need to '
           'decide this value carefully since it depends on the platform and '
           'antenna config to test.'), default=10),
      Arg('press_space_to_start', bool, 'Press space to start the test.',
          default=True),
      Arg('wifi_chip_type', str,
          ('The type of wifi chip. Indicates how the chip test the signal '
           'strength of different antennas. Currently, the valid options are '
           '``switch_antenna``, ``radiotap``, or ``disable_switch``. If the '
           'value is None, it will detect the value automatically.'),
          default=None),
      Arg('keep_monitor', bool,
          ('Set to True for WiFi driver that does not support '
           '``iw dev antmon0 del``.'), default=False),
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)

    self._dut = device_utils.CreateDUTInterface()
    self._device_name = None
    self._phy_name = None
    self._services = [wifi.ServiceSpec(ssid, freq, password)
                      for ssid, freq, password in self.args.services]
    self.assertTrue(self._services, 'At least one service should be specified.')
    self._wifi_chip_type = None
    self._wifi_chip = None

    if (self.args.wifi_chip_type == 'disable_switch' and
        list(self.args.strength) != ['all']):
      self.FailTask('Switching antenna is disabled but antenna configs are %s' %
                    list(self.args.strength))

    # Group checker for Testlog.
    self._service_group_checker = testlog.GroupParam(
        'service_signal', ['service', 'service_strength'])
    testlog.UpdateParam('service', param_type=testlog.PARAM_TYPE.argument)
    self._antenna_group_checker = testlog.GroupParam(
        'antenna', ['antenna', 'freq', 'strength'])
    testlog.UpdateParam('antenna', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('freq', param_type=testlog.PARAM_TYPE.argument)

  def tearDown(self):
    """Restores wifi states."""
    if self._wifi_chip:
      self._wifi_chip.Destroy()

  def _ChooseMaxStrengthService(self):
    """Chooses the service that has the largest signal strength among services.

    Returns:
      The service that has the largest signal strength among services.
    """
    max_strength_service, max_strength = None, -sys.float_info.max
    for service in self._services:
      strength = self._wifi_chip.GetAverageSignal(service, 'all')
      if strength:
        session.console.info('Service %s signal strength %f.', service,
                             strength)
        event_log.Log('service_signal', service=service.ssid, strength=strength)
        with self._service_group_checker:
          testlog.LogParam('service', service.ssid)
          testlog.LogParam('service_strength', strength)
        if strength > max_strength:
          max_strength_service, max_strength = service, strength
      else:
        session.console.info('Service %s has no valid signal strength.',
                             service)

    if max_strength_service:
      session.console.info('Service %s has the highest signal strength %f '
                           'among %s.', max_strength_service, max_strength,
                           self._services)
      return max_strength_service
    session.console.warning('Services %s are not valid.', self._services)
    return None

  def _ScanSignals(self, services, antenna):
    """Scans and averages signal strengths for services.

    Args:
      services: A list of (service_ssid, freq) tuples to scan.
      antenna: The antenna config to scan.
    """
    for service in services:
      self.ui.SetState(
          _('Scanning on device {device} frequency {freq}...',
            device=self._device_name,
            freq=service.freq))

      self._wifi_chip.ScanSignal(service, antenna, self.args.scan_count)

      self.ui.SetState(
          _('Done scanning on device {device} frequency {freq}...',
            device=self._device_name,
            freq=service.freq))

  def _CheckSpec(self, service, spec_antenna_strength, antenna):
    """Checks if the scan result of antenna config can meet test spec.

    Args:
      service: (service_ssid, freq, password) tuple.
      spec_antenna_strength: A dict of minimal signal strengths.
      antenna: The antenna config to check.
    """
    session.console.info('Checking antenna %s spec', antenna)
    scanned_strength = self._wifi_chip.GetAverageSignal(service, antenna)
    spec_strength = spec_antenna_strength[antenna]
    if not scanned_strength:
      self.FailTask(
          'Antenna %s, service: %s: Can not scan signal strength.' %
          (antenna, service))

    event_log.Log('antenna_%s' % antenna, freq=service.freq,
                  rssi=scanned_strength,
                  meet=(scanned_strength and scanned_strength >= spec_strength))
    with self._antenna_group_checker:
      testlog.LogParam('antenna', antenna)
      testlog.LogParam('freq', service.freq)
      result = testlog.CheckNumericParam('strength', scanned_strength,
                                         min=spec_strength)
    if not result:
      self.FailTask(
          'Antenna %s, service: %s: The scanned strength %f < spec strength'
          ' %f' % (antenna, service, scanned_strength, spec_strength))
    else:
      session.console.info(
          'Antenna %s, service: %s: The scanned strength %f >= spec strength'
          ' %f', antenna, service, scanned_strength, spec_strength)

  def _DetectWiFiChipType(self):
    self.ui.SetState(_('Detecting wifi chip type...'))

    self._wifi_chip_type = self.args.wifi_chip_type
    if not self._wifi_chip_type or self._wifi_chip_type == 'switch_antenna':
      self._wifi_chip = SwitchAntennaWiFiChip(
          self._dut, self._device_name, self._phy_name, self._services,
          self.args.switch_antenna_config, self.args.switch_antenna_sleep_secs,
          self.args.scan_timeout)
      if self._wifi_chip_type:
        return
      # If wifi_chip_type is not specified and the device is able to switch
      # antenna then we assume the chip type is switch_antenna.
      last_success_antenna = None
      for antenna in self.args.strength:
        try:
          self._wifi_chip.SwitchAntenna(antenna)
          last_success_antenna = antenna
        except wifi.WiFiError as e:
          session.console.info('Unable to switch antenna to %s. %r', antenna, e)
          break
      else:
        # All antennas are switchable.
        self._wifi_chip_type = 'switch_antenna'
        return
      if last_success_antenna:
        # Switch back to antenna all.
        try:
          self._wifi_chip.SwitchAntenna('all')
        except wifi.WiFiError:
          session.console.info(
              'Unable to switch antenna to all after switch to %s.',
              last_success_antenna)
          raise

    if not self._wifi_chip_type or self._wifi_chip_type == 'radiotap':
      self._wifi_chip = RadiotapWiFiChip(
          self._dut, self._device_name, self._phy_name, self._services,
          self.args.connect_timeout, self.args.scan_timeout,
          self.args.keep_monitor)
      self._wifi_chip_type = 'radiotap'
      return

    if self._wifi_chip_type == 'disable_switch':
      self._wifi_chip = DisableSwitchWiFiChip(
          self._dut, self._device_name, self._phy_name, self._services,
          self.args.switch_antenna_config, self.args.switch_antenna_sleep_secs,
          self.args.scan_timeout)
      return

    raise ValueError('Wifi chip type %s is not supported.' %
                     self._wifi_chip_type)

  def _ScanAllServices(self):
    self.ui.SetState(_('Checking frequencies...'))

    scan_result = self._dut.wifi.FilterAccessPoints(
        interface=self._device_name, scan_timeout=self.args.scan_timeout)
    ssid_freqs = {service.ssid: set() for service in self._services}

    for scanned_service in scan_result:
      if scanned_service.ssid in ssid_freqs:
        ssid_freqs[scanned_service.ssid].add(scanned_service.frequency)

    # Make a copy of the list because we might delete services in the loop.
    for service in list(self._services):
      if not ssid_freqs[service.ssid]:
        if self.args.ignore_missing_services:
          logging.info(
              'The service %s is not found. '
              'Ignore this service and continue the test.', service.ssid)
          self._services.remove(service)
          continue
        self.FailTask('The service %s is not found.' % service.ssid)
      elif service.freq is None:
        if len(ssid_freqs[service.ssid]) > 1:
          self.FailTask('There are more than one frequencies (%r) for ssid %s. '
                        'Please specify the frequency explicitly.' %
                        (ssid_freqs[service.ssid], service.ssid))
        service.freq = ssid_freqs[service.ssid].pop()
      elif service.freq not in ssid_freqs[service.ssid]:
        self.FailTask('Frequency %s is not supported by the service %s.  '
                      'Available frequencies are %r.' %
                      (service.freq, service.ssid, ssid_freqs[service.ssid]))

  def runTest(self):
    self._device_name = self._dut.wifi.SelectInterface(self.args.device_name)
    session.console.info('Selected device_name is %s.', self._device_name)

    self._phy_name = self._dut.wifi.DetectPhyName(self._device_name)
    session.console.info('phy name is %s.', self._phy_name)

    if self.args.press_space_to_start:
      # Prompts a message to tell operator to press space key when ready.
      self.ui.SetState(_('Press space to start scanning.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self._ScanAllServices()

    self._DetectWiFiChipType()
    session.console.info('Wifi chip type is %s.', self._wifi_chip_type)

    # Scans using antenna 'all'.
    self._ScanSignals(self._services, 'all')

    # Gets the service with the largest strength to test for each spec.
    test_service = self._ChooseMaxStrengthService()
    if test_service is None:
      self.FailTask('Services %s are not valid.' % self.args.services)

    # Checks 'all' since we have scanned using antenna 'all' already.
    self._CheckSpec(test_service, self.args.strength, 'all')

    # Scans and tests for other antenna config.
    for antenna in self.args.strength:
      if antenna == 'all':
        continue
      self._ScanSignals(self._services, antenna)
      self._CheckSpec(test_service, self.args.strength, antenna)
