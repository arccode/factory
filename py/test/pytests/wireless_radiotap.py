# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for checking Wifi antenna for Intel WP2 7260 chip.

Description
-----------
The test calculates the average RSSI values for each antenna by decoding
the radiotap-wrapped beacon frames sent by the AP service.

Be sure to set AP correctly.
1. Select one fixed channel instead of auto.
2. Disable the TX power control in AP.
3. Make sure SSID of AP is unique.

Test Procedure
--------------
The test accepts a list of wireless service specs.

1. For each service candidate, the test does following steps:

   a. Connect to that service.
   b. Monitor the beacon frame sent by the AP in radiotap format.
   c. Calculate the average RSSI values of each antenna.

2. Among all RSSI results, the test chooses the one whose antenna_all signal
   strength is the largest for checking the spec.

Dependency
----------
- `iw` utility
- `ip` utility
- `tcpdump` utility

Examples
--------
To run this test on DUT, add a test item in the test list::

  {
    "pytest_name": "wireless_radiotap",
    "args": {
      "services": [
        ["my_ap_service", 5300, "wifi_password"]
      ]
    }
  }

If the wifi service only serves one frequency (you can check by
``iw wlan0 scan``), you can also ask the test to detect the frequency value
by the ``iw scan`` command::

  {
    "pytest_name": "wireless_radiotap",
    "args": {
      "services": [
        ["my_ap_service", None, "wifi_password"]
      ]
    }
  }

"""

import collections
import re
import struct
import subprocess
import sys
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import wifi
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


_RE_IWSCAN = re.compile(r'freq: (\d+).*SSID: (.+)$')
_RE_WIPHY = re.compile(r'wiphy (\d+)')
_RE_BEACON = re.compile(r'(\d+) MHz.*Beacon \((.+)\)')

_ANTENNA_CONFIG = ['all', 'main', 'aux']


class ServiceSpec(type_utils.Obj):
  def __init__(self, ssid, freq, password):
    super(ServiceSpec, self).__init__(ssid=ssid, freq=freq, password=password)

  def __hash__(self):
    return hash((self.ssid, self.freq, self.password))


def IwScan(dut, iw_scan_group_checker, devname,
           sleep_retry_time_secs=2, max_retries=10):
  """Scans on device.

  Args:
    devname: device name.
    sleep_retry_time_secs: The sleep time before a retry.
    max_retries: The maximum retry time to scan.
  Returns:
    A list of `ServiceSpec` instance.

  Raises:
    IwException if fail to scan for max_retries tries,
    or fail because of reason other than device or resource busy (-16)
  """
  cmd = ("iw %s scan | grep -e '^\\s*\\(freq\\|SSID\\):' | sed 'N;s/\\n/ /'" %
         devname)
  for unused_try_count in xrange(max_retries):
    process = dut.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        log=True)
    stdout, stderr = process.communicate()
    retcode = process.returncode
    event_log.Log('iw_scaned', retcode=retcode, stderr=stderr)
    with iw_scan_group_checker:
      testlog.LogParam('retcode', retcode)
      testlog.LogParam('stderr', stderr)

    if retcode == 0:
      scan_result = []
      for line in stdout.splitlines():
        m = _RE_IWSCAN.search(line)
        if m:
          scan_result.append(ServiceSpec(m.group(2), int(m.group(1)), None))
      if scan_result:
        session.console.info('IwScan success.')
        return scan_result
    elif retcode == 234:  # Invalid argument (-22)
      raise Exception('Failed to iw scan, ret code: %d. stderr: %s'
                      'Frequency might be wrong.' %
                      (retcode, stderr))
    elif retcode != 240:  # Device or resource busy (-16)
      raise Exception('Failed to iw scan, ret code: %d. stderr: %s' %
                      (retcode, stderr))
    time.sleep(sleep_retry_time_secs)
  raise Exception('Failed to iw scan for %s tries' % max_retries)


class RadiotapPacket(object):
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
  EXPECTED_HEADER_FORMAT = struct.Struct(MAIN_HEADER_FORMAT.format + 'II')

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

  def __init__(self, dut, device_name, phy):
    self.dut = dut
    self.monitor_process = None
    self.created_device = None
    self.parent_device = device_name
    self.phy = phy

  def CreateDevice(self, monitor_device='antmon0'):
    """Creates a monitor device to monitor beacon."""
    self.dut.CheckCall(['iw', self.parent_device, 'interface', 'add',
                        monitor_device, 'type', 'monitor'], log=True)
    self.created_device = monitor_device

  def RemoveDevice(self, device_name):
    """Removes monitor device."""
    self.dut.CheckCall(['iw', device_name, 'del'], log=True)

  def GetSignal(self):
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
      # "\xab\xcd\xef".
      parts = line[3:].split()
      for part in parts[1:]:
        packet_bytes += chr(int(part[:2], 16))
        if len(part) > 2:
          packet_bytes += chr(int(part[2:], 16))
      packet = RadiotapPacket.Decode(packet_bytes)
      if packet:
        return {'ssid': ssid, 'freq': freq, 'signal': packet}

  def set_beacon_filter(self, value):
    """Sets beacon filter.

    This function may only for Intel WP2 7260 chip.
    """
    path = '/sys/kernel/debug/ieee80211/%s/netdev:%s/iwlmvm/bf_params' % (
        self.phy, self.parent_device)
    self.dut.WriteFile(path, 'bf_enable_beacon_filter=%d\n' % value)

  def __enter__(self):
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
    return self

  def __exit__(self, exception, value, traceback):
    self.monitor_process.kill()
    self.set_beacon_filter(1)
    if self.created_device:
      self.RemoveDevice(self.created_device)


class WirelessRadiotapTest(test_case.TestCase):
  """Basic wireless test class.

  Properties:
    _antenna: current antenna config.
    _phy_name: wireless phy name to test.
  """
  ARGS = [
      Arg('device_name', str,
          'Wireless device name to test. ', default='wlan0'),
      Arg('services', list,
          'A list of ``(<service_ssid>:str, <freq>:str|None, '
          '<password>:str|None)`` tuples like ``[(SSID1, FREQ1, PASS1), '
          '(SSID2, FREQ2, PASS2), ...]``.  If ``<freq>`` is ``None`` the test '
          'will detect the frequency by ``iw <device_name> scan`` command '
          'automatically.  ``<password>=None`` implies the service can connect '
          'without a password.'),
      Arg('connect_timeout', int,
          'Timeout for connecting to the service.',
          default=10),
      Arg('strength', dict,
          'A dict of minimal signal strengths. For example, a dict like '
          '``{"main": strength_1, "aux": strength_2, "all": strength_all}``. '
          'The test will check signal strength according to the different '
          'antenna configurations in this dict.'),
      Arg('scan_count', int,
          'Number of scans to get average signal strength.', default=5),
      Arg('press_space_to_start', bool,
          'Press space to start the test.', default=True)]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)

    self._dut = device_utils.CreateDUTInterface()
    self._phy_name = None
    self._ap = None
    self._connection = None
    self._services = [ServiceSpec(ssid, freq, password)
                      for ssid, freq, password in self.args.services]
    self.assertTrue(self._services, 'At least one service should be specified.')

    # Group checker for Testlog.
    self._iw_scan_group_checker = testlog.GroupParam(
        'iw_scan', ['retcode', 'stderr'])
    self._service_group_checker = testlog.GroupParam(
        'service_signal', ['service', 'service_strength'])
    testlog.UpdateParam('service', param_type=testlog.PARAM_TYPE.argument)
    self._antenna_group_checker = testlog.GroupParam(
        'antenna', ['antenna', 'freq', 'strength'])
    testlog.UpdateParam('antenna', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('freq', param_type=testlog.PARAM_TYPE.argument)

  def tearDown(self):
    self._DisconnectService()

  def _ConnectService(self, service_name, password):
    """Associates a specified wifi AP.

    Password can be '' or None.
    """
    try:
      self._ap = self._dut.wifi.FindAccessPoint(ssid=service_name)
    except wifi.WifiError as e:
      session.console.info(
          'Unable to find the service %s: %r' % (service_name, e))
      return False

    try:
      self._connection = self._dut.wifi.Connect(
          self._ap, passkey=password, connect_timeout=self.args.connect_timeout)
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

  def _DetectPhyName(self):
    """Detects the phy name for device_name device.

    Returns:
      The phy name for device_name device.
    """
    output = self._dut.CheckOutput(
        ['iw', 'dev', self.args.device_name, 'info'], log=True)
    m = _RE_WIPHY.search(output)
    return ('phy' + m.group(1)) if m else None

  def _ChooseMaxStrengthService(self, service_strengths):
    """Chooses the service that has the largest signal strength among services.

    Args:
      services: A list of services.
      service_strengths: A dict of strengths of each service.

    Returns:
      The service that has the largest signal strength among services.
    """
    max_strength_service, max_strength = None, -sys.float_info.max
    for service in self._services:
      strength = service_strengths[service]['all']
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
    else:
      session.console.warning('Services %s are not valid.', self._services)
      return None

  def _ScanSignal(self, service, times=3):
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
    self.ui.SetState(_('Switching to AP {ap}...', ap=service.ssid))
    if not self._ConnectService(service.ssid, service.password):
      return []

    self.ui.SetState(
        _('Scanning on device {device} frequency {freq}...',
          device=self.args.device_name,
          freq=service.freq))
    with Capture(self._dut, self.args.device_name, self._phy_name) as capture:
      capture_times = 0
      while capture_times < times:
        signal_result = capture.GetSignal()
        if (signal_result['ssid'] == service.ssid and
            signal_result['freq'] == service.freq):
          session.console.info('%s', signal_result)
          signal_list.append(signal_result['signal'])
          capture_times += 1
        else:
          session.console.info('Ignore the signal %r', signal_result)
    self.ui.SetState(
        _('Done scanning on device {device} frequency {freq}...',
          device=self.args.device_name,
          freq=service.freq))
    self._DisconnectService()
    return signal_list

  def _AverageSignals(self, antenna_info):
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
    average_results = {}
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
          if antenna_info else None)
    return average_results

  def _CheckSpec(self, service, spec_antenna_strength, average_signal):
    """Checks if the scan result of antenna config can meet test spec.

    Args:
      service: (service_ssid, freq, password) tuple.
      spec_antenna_strength: A dict of minimal signal strengths.
      average_signal: A dict of average signal strength of each service in
          service. {service: {antenna1: signal1, antenna2: signal2}}
    """
    for antenna in _ANTENNA_CONFIG:
      if spec_antenna_strength.get(antenna) is None:
        continue
      spec_strength = spec_antenna_strength[antenna]
      scanned_strength = average_signal[service][antenna]
      if not scanned_strength:
        self.FailTask(
            'Antenna %s, service: %s: Can not scan signal strength.' %
            (antenna, service))

      event_log.Log(
          'antenna_%s' % antenna, freq=service.freq,
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
            'Antenna %s, service: %s: The scanned strength %f > spec strength'
            ' %f', antenna, service, scanned_strength, spec_strength)

  def _ScanAllServices(self):
    self.ui.SetState(_('Checking frequencies...'))

    scan_result = IwScan(
        self._dut, self._iw_scan_group_checker, self.args.device_name)
    ssid_freqs = {service.ssid : set() for service in self._services}

    for scanned_service in scan_result:
      if scanned_service.ssid in ssid_freqs:
        ssid_freqs[scanned_service.ssid].add(scanned_service.freq)

    for service in self._services:
      if not ssid_freqs[service.ssid]:
        self.FailTask('The service %s is not found.' % service.ssid)
      elif service.freq is None:
        if len(ssid_freqs[service.ssid]) > 1:
          self.FailTask('There are more than one frequencies (%r) for ssid %s. '
                        'Please specify the frequency explicity.' %
                        (ssid_freqs[service.ssid], service.ssid))
        service.freq = ssid_freqs[service.ssid].pop()
      elif service.freq not in ssid_freqs[service.ssid]:
        self.FailTask('Frequency %s is not supported by the service %s.  '
                      'Available frequencies are %r.' %
                      (service.freq, service.ssid, ssid_freqs[service.ssid]))

  def runTest(self):
    self._phy_name = self._DetectPhyName()
    session.console.info('phy name is %s.', self._phy_name)

    if self.args.press_space_to_start:
      self.ui.SetState(_('Press space to start scanning.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self._ScanAllServices()

    average_signal = {}
    for service in self._services:
      signals = self._ScanSignal(service, self.args.scan_count)
      average_signal[service] = self._AverageSignals(signals)

    # Gets the service with the largest strength to test for each spec.
    test_service = self._ChooseMaxStrengthService(average_signal)
    if test_service is None:
      self.FailTask('Services %s are not valid.' % self.args.services)
    else:
      self._CheckSpec(test_service, self.args.strength, average_signal)
