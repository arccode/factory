# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for checking Wifi antenna.

The test accepts a dict of wireless specs.
Each spec contains candidate services and the signal constraints.
For each spec, the test will connect to AP first.
And scan the signal quality to get signal strength for all antennas.
Then the test checks signal quality.

Be sure to set AP correctly.
1. Select one fixed channel instead of auto.
2. Disable the TX power control in AP.
3. Make sure SSID of AP is unique.

This test case can be used for Intel WP2 7260 chip.
"""

import dbus
import collections
import logging
import re
import struct
import sys
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.process_utils import CheckOutput, Spawn, PIPE
from cros.factory.utils.net_utils import Ifconfig

try:
  sys.path.append('/usr/local/lib/flimflam/test')
  import flimflam  # pylint: disable=F0401
except: # pylint: disable=W0702
  pass

_DEFAULT_WIRELESS_TEST_CSS = '.wireless-info {font-size: 2em;}'

_MSG_SWITCHING_AP = lambda ap: test_ui.MakeLabel(
    'Switching to AP %s: ' % ap,
    u'切换到基地台 %s...' % ap,
    'wireless-info')
_MSG_SCANNING = lambda device, freq: test_ui.MakeLabel(
    'Scanning on device %s frequency %d...' % (device, freq),
    u'在装置 %s 上扫描频率%d...' % (device, freq),
    'wireless-info')
_MSG_SCANNING_DONE = lambda device, freq: test_ui.MakeLabel(
    'Done scanning on device %s frequency %d...' % (device, freq),
    u'在装置 %s 上扫描频率%d 完成' % (device, freq),
    'wireless-info')
_MSG_SPACE = test_ui.MakeLabel(
    'Press space to start scanning.',
    u'请按空白键开始扫描。', 'wireless-info')
_MSG_PRECHECK = test_ui.MakeLabel(
    'Checking frequencies...',
    u'檢查頻率中...', 'wireless-info')

_RE_IWSCAN = re.compile('freq: (\d+).*SSID: (.+)$')
_RE_WIPHY = re.compile(r'wiphy (\d+)')
_RE_BEACON = re.compile('(\d+) MHz.*Beacon \((.+)\)')

_ANTENNA_CONFIG = ['all', 'main', 'aux']


def FlimGetService(flim, name):
  """Get service by property.

  Args:
    flim: flimflam object
    name: property name
  """
  timeout = time.time() + 10
  while time.time() < timeout:
    service = flim.FindElementByPropertySubstring('Service', 'Name', name)
    if service:
      return service
    time.sleep(0.5)


def FlimGetServiceProperty(service, prop):
  """Get property from a service.

  Args:
    service: flimflam service object
    prop: property name
  """
  timeout = time.time() + 10
  while time.time() < timeout:
    try:
      properties = service.GetProperties()
    except dbus.exceptions.DBusException as e:
      logging.exception('Error reading service property')
      time.sleep(1)
    else:
      return properties[prop]
  raise e


def FlimConfigureService(flim, ssid, password):
  """Config wireless ssid and password.

  Args:
    ssid: ssid name
    password: wifi key to authenticate
  """
  wlan_dict = {
      'Type': 'wifi',
      'Mode': 'managed',
      'AutoConnect': False,
      'SSID': ssid}
  if password:
    wlan_dict['Security'] = 'psk'
    wlan_dict['Passphrase'] = password

  flim.manager.ConfigureService(wlan_dict)


def IwScan(devname, sleep_retry_time_secs=2, max_retries=10):
  """Scans on device.

  Args:
    devname: device name.
    sleep_retry_time_secs: The sleep time before a retry.
    max_retries: The maximum retry time to scan.
  Returns:
    A list of (ssid, frequency) tuple.

  Raises:
    IwException if fail to scan for max_retries tries,
    or fail because of reason other than device or resource busy (-16)
  """
  cmd = "iw %s scan | grep -e 'freq\|SSID' | sed 'N;s/\\n/ /'" % devname
  try_count = 0
  scan_result = []
  while try_count < max_retries:
    process = Spawn(cmd, read_stdout=True, log_stderr_on_error=True,
                    log=True, shell=True)
    stdout, stderr = process.communicate()
    retcode = process.returncode
    Log('iw_scaned', retcode=retcode, stderr=stderr)
    if retcode == 0:
      for line in stdout.splitlines():
        m = _RE_IWSCAN.search(line)
        if m:
          scan_result.append((m.group(2), m.group(1)))
      if len(scan_result) == 0:
        try_count += 1
        time.sleep(sleep_retry_time_secs)
        continue
      logging.info('IwScan success.')
      return scan_result
    elif retcode == 240:  # Device or resource busy (-16)
      try_count += 1
      time.sleep(sleep_retry_time_secs)
    elif retcode == 234:  # Invalid argument (-22)
      raise Exception('Failed to iw scan, ret code: %d. stderr: %s'
                        'Frequency might be wrong.' %
                        (retcode, stderr))
    else:
      raise Exception('Failed to iw scan, ret code: %d. stderr: %s' %
                        (retcode, stderr))
  raise Exception('Failed to iw scan for %s tries' % max_retries)


class RadiotapPacket(object):
  FIELD = collections.namedtuple('Field', [ 'name', 'struct', 'align' ])
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
      FIELD('MCS', struct.Struct('BBB'), 1),
      FIELD('AMPDU status', struct.Struct('IHBB'), 4),
      FIELD('VHT', struct.Struct('HBBBBBBBBH'), 2),]
  MAIN_HEADER_FORMAT = struct.Struct('BBhI')
  PARSE_INFO = collections.namedtuple('AntennaData', ['header_size',
      'data_bytes',
      'antenna_offsets'])

  # This is a variable-length header, but this is what we want to see.
  EXPECTED_HEADER_FORMAT = struct.Struct(MAIN_HEADER_FORMAT.format + 'II')

  @staticmethod
  def decode(packet_bytes):
    """Returns signal strength data for each antenna.

    Format is {all_signal, {antenna_index, antenna_signal}}.
    """
    if len(packet_bytes) < RadiotapPacket.EXPECTED_HEADER_FORMAT.size:
      return None
    parts = RadiotapPacket.EXPECTED_HEADER_FORMAT.unpack_from(packet_bytes)
    (_, _, _, present0, present1, present2) = parts
    parse_info = RadiotapPacket.parse_header([present0, present1, present2])
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
  def parse_header(field_list):
    """Returns packet information of the radiotap header should have."""
    header_size = RadiotapPacket.MAIN_HEADER_FORMAT.size
    data_bytes = 0
    antenna_offsets = []

    for _, bitmask in enumerate(field_list):
      antenna_offsets.append({})
      for bit, field in enumerate(RadiotapPacket.FIELDS):
        if bitmask & (1 << bit):
          if field.align and (data_bytes % field.align):
            data_bytes += field.align - (data_bytes % field.align)
          if (field == RadiotapPacket.ANTENNA_SIGNAL_FIELD or
              field == RadiotapPacket.ANTENNA_INDEX_FIELD):
            antenna_offsets[-1][field] = data_bytes
          data_bytes += field.struct.size

      if not bitmask & (1 << RadiotapPacket.EXTENDED_BIT):
        break
      header_size += 4
    else:
      raise NotImplementedError('Packet has too many extensions for me!')

    # Offset the antenna fields by the header size.
    return RadiotapPacket.PARSE_INFO(header_size, data_bytes, antenna_offsets)


class Capture(object):
  """Context for a live tcpdump packet capture for beacons."""
  def __init__(self, device_name, phy):
    self.monitor_process = None
    self.created_device = None
    self.parent_device = device_name
    self.phy = phy

  def create_device(self, monitor_device='antmon0'):
    """Creates a monitor device to monitor beacon."""
    Spawn(['iw', self.parent_device, 'interface', 'add',
        monitor_device, 'type', 'monitor'], check_call=True)
    self.created_device = monitor_device

  def remove_device(self, device_name):
    """Removes monitor device."""
    Spawn(['iw', device_name, 'del'], check_call=True)

  def get_signal(self):
    """Gets signal from tcpdump."""
    while True:
      line = self.monitor_process.stdout.readline()
      m = _RE_BEACON.search(line)
      if m:
        freq = int(m.group(1))
        ssid = m.group(2)
        break
    packet_bytes = ''
    while True:
      line = self.monitor_process.stdout.readline()
      if not line.startswith('\t0x'):
        break

      # Break up lines of the form "\t0x0000: abcd ef" into a string
      # "\xab\xcd\exef".
      parts = line[3:].split()
      for part in parts[1:]:
        packet_bytes += chr(int(part[:2], 16))
        if len(part) > 2:
          packet_bytes += chr(int(part[2:], 16))
      packet = RadiotapPacket.decode(packet_bytes)
      if packet:
        return {'ssid': ssid, 'freq': freq, 'signal': packet}

  def set_beacon_filter(self, value):
    """Sets beacon filter.

    This function may only for Intel WP2 7260 chip.
    """
    with open('/sys/kernel/debug/ieee80211/%s/netdev:%s/iwlmvm/bf_params' %
        (self.phy, self.parent_device), 'w') as f:
      f.write('bf_enable_beacon_filter=%d\n' % value)

  def __enter__(self):
    if not self.created_device:
      self.create_device()
    Spawn(['ip', 'link', 'set', self.created_device, 'up'], check_call=True)
    Spawn(['iw', self.parent_device, 'set', 'power_save', 'off'],
        check_call=True)
    self.set_beacon_filter(0)
    self.monitor_process = Spawn(['tcpdump', '-nUxxi', self.created_device,
        'type', 'mgt', 'subtype', 'beacon'], stdout=PIPE)
    return self

  def __exit__(self, exception, value, traceback):
    self.monitor_process.kill()
    self.set_beacon_filter(1)
    if self.created_device:
      self.remove_device(self.created_device)


class WirelessRadiotapTest(unittest.TestCase):
  """Basic wireless test class.

  Properties:
    _ui: Test ui.
    _template: Test template.
    _antenna: current antenna config.
    _phy_name: wireless phy name to test.
    _test_spec: the reduced version of spec_dict. The candidate services in
        spec_dict.keys() are replaced by the services with the largest strength.
    _space_event: An event that space has been pressed. It will also be set
        if test has been done.
    _done: An event that test has been done.
  """
  ARGS = [
    Arg('device_name', str, 'wireless device name to test.'
        'Set this correctly if check_antenna is True.', default='wlan0'),
    Arg('spec_dict', dict, 'Keys: a tuple of (service_ssid, freq, password) '
        'tuples like ((SSID_AP1, FREQ_AP1, PASS_AP1), (SSID_AP2, FREQ_AP2, '
        'PASS_AP2), (SSID_AP3, FREQ_AP3, PASS_AP3)). '
        'The test will only check the service whose antenna_all signal strength'
        ' is the largest. If (SSID_AP1, FREQ_AP1) has the largest signal among '
        'AP1, AP2, AP3, then its result will be checked against the spec value.'
        ' Values: a dict of minimal signal strength. For example, a dict like '
        '{"main": strength_1, "aux": strength_2, "all": strength_all}. '
        'The test will check signal strength under different antenna config. '
        'Example of spec_dict: { '
        '    ((SSID_AP1, FREQ_AP1, PASS_AP1), (SSID_AP2, FREQ_AP2, PASS_AP2)): '
        '        {"all": 50, "main": 50, "aux": 50}, '
        '    ((SSID_AP3, FREQ_AP3, PASS_AP3)): {"all": 60}}.',
        optional=False),
    Arg('scan_count', int, 'number of scanning to get average signal strength',
        default=5),
    Arg('switch_antenna_sleep_secs', int, 'The sleep time after switching'
        'antenna and ifconfig up. Need to decide this value carefully since it'
        'depends on the platform and antenna config to test.', default=10)
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = OneSection(self._ui)
    self._ui.AppendCSS(_DEFAULT_WIRELESS_TEST_CSS)

    self._phy_name = self.DetectPhyName()
    logging.info('phy name is %s.', self._phy_name)
    self._test_spec = dict()
    self._space_event = threading.Event()
    self._done = threading.Event()

    Ifconfig(self.args.device_name, True)
    self._flim = flimflam.FlimFlam(dbus.SystemBus())
    self._connect_service = None

  def tearDown(self):
    self.DisconnectService()

  def ConnectService(self, service_name, password):
    """Associates a specified wifi AP.

    Password can be '' or None.
    """
    self._connect_service = FlimGetService(self._flim, service_name)
    if self._connect_service is None:
      factory.console.info('Unable to find service %s' % service_name)
      return False
    if FlimGetServiceProperty(self._connect_service, 'IsActive'):
      logging.warning('Already connected to %s', service_name)
    else:
      logging.info('Connecting to %s', service_name)
      FlimConfigureService(self._flim, service_name, password)
      success, diagnostics = self._flim.ConnectService(
          service=self._connect_service)
      if not success:
        factory.console.info('Unable to connect to %s, diagnostics %s' %
            (service_name, diagnostics))
        return False
      else:
        factory.console.info(
            'Successfully connected to service %s' % service_name)
    return True

  def DisconnectService(self):
    """Disconnect wifi AP."""
    if self._connect_service:
      self._flim.DisconnectService(service=self._connect_service)
      factory.console.info('Disconnect to service %s' %
          FlimGetServiceProperty(self._connect_service, 'Name'))
      self._connect_service = None

  def DetectPhyName(self):
    """Detects the phy name for device_name device.

    Returns:
      The phy name for device_name device.
    """
    output = CheckOutput(['iw', 'dev', self.args.device_name, 'info'])
    logging.info('info output: %s', output)
    m = _RE_WIPHY.search(output)
    return ('phy' + m.group(1)) if m else None

  def ChooseMaxStrengthService(self, services, service_strengths):
    """Chooses the service that has the largest signal strength among services.

    Args:
      services: A list of services.
      service_strengths: A dict of strengths of each service.

    Returns:
      The service that has the largest signal strength among services.
    """
    max_strength_service, max_strength = None, -sys.float_info.max
    for service in services:
      strength = service_strengths[service]['all']
      if strength:
        factory.console.info('Service %s signal strength %f.', service,
                             strength)
        Log('service_signal', service=service, strength=strength)
        if strength > max_strength:
          max_strength_service, max_strength = service, strength
      else:
        factory.console.info('Service %s has no valid signal strength.',
                             service)

    if max_strength_service:
      logging.info('Service %s has the highest signal strength %f among %s.',
                   max_strength_service, max_strength, services)
      return max_strength_service
    else:
      logging.warning('Services %s are not valid.', services)

  def ScanSignal(self, service, times=3):
    """Scans antenna signal strengths for a specified service.

    Device should connect to the service before starting to capture signal.
    Signal result only includes antenna information of this service
    (ssid, freq).

    Args:
      service: (service_ssid, freq, password) tuple.
      times: Number of times to scan to get average.

    Returns:
      A list of signal result.
    """
    signal_list = []
    (ssid, freq, password) = service
    self._template.SetState(_MSG_SWITCHING_AP(ssid))
    result = self.ConnectService(ssid, password)
    if result is False:
      return []

    self._template.SetState(_MSG_SCANNING(self.args.device_name, freq))
    with Capture(self.args.device_name, self._phy_name) as capture:
      capture_times = 0
      while capture_times < times:
        signal_result = capture.get_signal()
        if signal_result['ssid'] == ssid and signal_result['freq'] == freq:
          logging.info('%s', signal_result)
          signal_list.append(signal_result['signal'])
          capture_times += 1
    self._template.SetState(
        _MSG_SCANNING_DONE(self.args.device_name, freq))
    self.DisconnectService()
    return signal_list

  def AverageSignals(self, antenna_info):
    """Averages signal strengths for each antenna of a service.

    The dividend is the sum of signal strengths during all scans.
    The divisor is the number of times in the scan result.
    If a service is not scannable, its average value will be None.

    Args:
      antenna_info: A dict of each antenna information of a service.

    Returns:
      A dict of average signal strength of each antenna.
      {antenna1: signal1, antenna2: signal2}
    """
    # keys are services and values are averages
    average_results = dict()
    # Averages the scanned strengths
    for antenna in _ANTENNA_CONFIG:
      average_results[antenna] = 0
    for signal in antenna_info:
      average_results['all'] += signal[0]
      average_results['main'] += signal[1][1]
      average_results['aux'] += signal[2][1]
    for antenna in _ANTENNA_CONFIG:
      average_results[antenna] = (
          float(average_results[antenna]) / len(antenna_info)
          if len(antenna_info) else None)
    return average_results

  def CheckSpec(self, average_signal):
    """Checks if the scan result of antenna config can meet test spec.

    Args:
      average_signal: A dict of average signal strength of each service in
          service. {service: {antenna1: signal1, antenna2: signal2}}
    """
    for test_service, spec_antenna_strength in self._test_spec.iteritems():
      for antenna in _ANTENNA_CONFIG:
        if spec_antenna_strength.get(antenna) is None:
          continue
        spec_strength = spec_antenna_strength[antenna]
        scanned_strength = average_signal[test_service][antenna]

        Log('antenna_%s' % antenna, freq=test_service[1], rssi=scanned_strength,
            meet=(scanned_strength and scanned_strength > spec_strength))
        if not scanned_strength:
          self.fail(
              'Antenna %s, service: %s: Can not scan signal strength.' %
              (antenna, test_service))
        if scanned_strength < spec_strength:
          self.fail(
              'Antenna %s, service: %s: The scanned strength %f < spec strength'
              ' %f' % (antenna, test_service, scanned_strength, spec_strength))
        else:
          factory.console.info(
              'Antenna %s, service: %s: The scanned strength %f > spec strength'
              ' %f', antenna, test_service, scanned_strength, spec_strength)

  def PreCheck(self, services):
    """Checks each service only has one frequency.

    Args:
      services: A list of (service_ssid, freq) tuples to scan.
    """
    wireless_services = dict()
    self._template.SetState(_MSG_PRECHECK)
    scan_result = IwScan(self.args.device_name)
    set_all_ssids = set([service[0] for service in services])

    for ssid, freq in scan_result:
      if ssid in set_all_ssids:
        if ssid not in wireless_services:
          wireless_services[ssid] = freq
        elif freq != wireless_services[ssid]:
          self.fail(
              'There are more than one frequencies for ssid %s.' % ssid)

  def PromptSpace(self):
    """Prompts a message to ask operator to press space."""
    self._template.SetState(_MSG_SPACE)
    self._ui.BindKey(' ', lambda _: self.OnSpacePressed())
    self._ui.Run(blocking=False, on_finish=self.Done)

  def Done(self):
    """The callback when ui is done.

    This will be called when test is finished, or if operator presses
    'Mark Failed'.
    """
    self._done.set()
    self._space_event.set()

  def OnSpacePressed(self):
    """The handler of space key."""
    logging.info('Space pressed by operator.')
    self._space_event.set()

  def runTest(self):
    # Prompts a message to tell operator to press space key when ready.
    self.PromptSpace()
    self._space_event.wait()
    if self._done.isSet():
      return

    # Gets all the candidate services and required antenna configs.
    set_all_services = set()
    for spec_services, _ in self.args.spec_dict.iteritems():
      set_all_services = set_all_services.union(set(spec_services))
    logging.info('All candidate services: %s', set_all_services)

    self.PreCheck(set_all_services)

    antenna_info = dict()
    for service in set_all_services:
      antenna_info[service] = self.ScanSignal(service, self.args.scan_count)
    average_signal = dict()
    for service, signals in antenna_info.iteritems():
      average_signal[service] = self.AverageSignals(signals)

    # Gets the service with the largest strength to test for each spec.
    for candidate_services, spec_strength in self.args.spec_dict.iteritems():
      test_service = self.ChooseMaxStrengthService(candidate_services,
          average_signal)
      if test_service is None:
        self.fail('Services %s are not valid.' % candidate_services)
      else:
        self._test_spec[test_service] = spec_strength
    self.CheckSpec(average_signal)
