# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for basic Wifi.

The test accepts a dict of wireless specs.
Each spec contains candidate services and the signal constraints.
For each spec, the test will first scan the signal quality using 'all' antenna
to determine the strongest service to test. Then the test switches antenna
configuration to test signal quality.
Be sure to set AP correctly.
1. Select a fixed channel instead of auto.
2. Disable the power control in AP.
3. Make sure mac address of AP is unique.
"""

import logging
import re
import sys
import threading
import time
import unittest

from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.process_utils import CheckOutput, Spawn

_DEFAULT_WIRELESS_TEST_CSS = '.wireless-info {font-size: 2em;}'

_MSG_SWITCHING_ANTENNA = lambda antenna: test_ui.MakeLabel(
    'Switching to antenna %s: ' % antenna,
    u'切换到天线 %s...' % antenna,
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

_RE_FREQ = re.compile(r'^freq: ([\d]*?)$')
_RE_SIGNAL = re.compile(r'^signal: ([-\d.]*?) dBm')
_RE_SSID = re.compile(r'^SSID: ([-\w]*)$')
_RE_WIPHY = re.compile(r'wiphy (\d+)')

def GetProp(message, pattern, default):
  """Gets the property from searching pattern in message.

  Args:
    message: A string to search for pattern.
    pattern: A regular expression object which will capture a value if pattern
             can be found. This object must have a group definition.
    default: Default value of property.
  """
  obj = pattern.search(message)
  return obj.group(1) if obj else default


class IwException(Exception):
  pass


def IfconfigUp(devname, sleep_time_secs=1):
  """Brings up interface.

  Args:
    devname: Device name.
    sleep_time_secs: The sleeping time after ifconfig up.
  """
  Spawn(['ifconfig', devname, 'up'], check_call=True, log=True)
  # Wait for device to settle down.
  time.sleep(sleep_time_secs)


def IfconfigDown(devname, sleep_time_secs=1):
  """Brings down interface.

  Args:
    devname: Device name.
    sleep_time_secs: The sleeping time after ifconfig down.
  """
  Spawn(['ifconfig', devname, 'down'], check_call=True, log=True)
  # Wait for device to settle down.
  time.sleep(sleep_time_secs)


def IwSetAntenna(devname, phyname, tx_bitmap, rx_bitmap, max_retries=10,
                 switch_antenna_sleep_secs=10):
  """Sets antenna using iw command.

  Args:
    devname: Device name.
    phyname: PHY name of the hardware.
    tx_bitmap: The desired tx bitmap of antenna.
    rx_bitmap: The desired rx bitmap of antenna.
    max_retries: The maximum retry time to set antenna.
    switch_antenna_sleep_secs: The sleep time after switching antenna and
        ifconfig up.
  Raises:
    IwException if fail to set antenna for max_retries tries.
  """
  IfconfigDown(devname)
  try_count = 0
  success = False
  while try_count < max_retries:
    process = Spawn(['iw', 'phy', phyname,
                     'set', 'antenna', tx_bitmap, rx_bitmap],
                     read_stdout=True, log_stderr_on_error=True, log=True)
    retcode = process.returncode
    if retcode == 0:
      success = True
      break
    # (-95) EOPNOTSUPP Operation not supported on transport endpoint
    # Do ifconfig down again may solve this problem.
    elif retcode == 161:
      try_count += 1
      factory.console.info('Retry...')
      IfconfigDown(devname)
    else:
      raise IwException('Failed to set antenna. ret code: %d. stderr: %s' %
                        (retcode, process.stderr))
  IfconfigUp(devname, switch_antenna_sleep_secs)
  if not success:
    raise IwException('Failed to set antenna for %s tries' % max_retries)


def IwScan(devname, frequency=None, sleep_retry_time_secs=2, max_retries=10):
  """Scans on device.

  Args:
    devname: device name.
    frequency: The desired scan frequency.
    sleep_retry_time_secs: The sleep time before a retry.
    max_retries: The maximum retry time to scan.
  Returns:
    scan stdout.

  Raises:
    IwException if fail to scan for max_retries tries,
    or fail because of reason other than device or resource busy (-16)
  """
  cmd = ['iw', 'dev', devname, 'scan']
  if frequency is not None:
    cmd += ['freq', str(frequency)]
  try_count = 0
  while try_count < max_retries:
    process = Spawn(cmd, read_stdout=True, log_stderr_on_error=True,
                    log=True)
    stdout, stderr = process.communicate()
    retcode = process.returncode
    Log('iw_scaned', retcode=retcode, stderr=stderr)
    if retcode == 0:
      logging.info('IwScan success.')
      return stdout
    elif retcode == 240:  # Device or resource busy (-16)
      try_count += 1
      time.sleep(sleep_retry_time_secs)
    elif retcode == 234:  # Invalid argument (-22)
      raise IwException('Failed to iw scan, ret code: %d. stderr: %s'
                        'Frequency might be wrong.' %
                        (retcode, stderr))
    else:
      raise IwException('Failed to iw scan, ret code: %d. stderr: %s' %
                        (retcode, stderr))
  raise IwException('Failed to iw scan for %s tries' % max_retries)

_ANTENNA_CONFIG = {'main': ('1', '1'),
                   'aux': ('2', '2'),
                   'all': ('3', '3')}


class WirelessTest(unittest.TestCase):
  """Basic wireless test class.

  Properties:
    _ui: Test ui.
    _template: Test template.
    _antenna: current antenna config.
    _phy_name: wireless phy name to test.
    _antenna_service_strength: a dict of dict to store the scan result
        of each service under each antenna config. e.g.
        {'all':{'AP1': -30, 'AP2': -40},
         'main': {'AP1': -40, 'AP2': -50},
         'aux': {'AP1': -40, 'AP2': -50}}
    _test_spec: the reduced version of spec_dict. The candidate services in
        spec_dict.keys() are replaced by the services with the largest strength.
    _space_event: An event that space has been pressed. It will also be set
        if test has been done.
    _done: An event that test has been done.
  """
  ARGS = [
    Arg('device_name', str, 'wireless device name to test.'
        'Set this correctly if check_antenna is True.', default='wlan0'),
    Arg('spec_dict', dict, 'Keys: a tuple of (service_macs, freq) tuples like '
        '((MAC_AP1, FREQ_AP1), (MAC_AP2, FREQ_AP2), (MAC_AP3, FREQ_AP3)). '
        'The test will only check the service whose antenna_all signal strength'
        ' is the largest. If (MAC_AP1, FREQ_AP1) has the largest signal among '
        'AP1, AP2, AP3, then its result will be checked against the spec value.'
        ' Values: a dict of minimal signal strength. For example, a dict like '
        '{"main": strength_1, "aux": strength_2, "all": strength_all}. '
        'The test will check signal strength under different antenna config. '
        'Example of spec_dict: {(MAC_AP1, MAC_AP2, MAC_AP3): {"all": 50}, '
        '((MAC_AP4, FREQ_AP4)): {"main": 50, "aux": 50, "all": 60)}.',
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
    self._antenna_service_strength = dict()
    for antenna in _ANTENNA_CONFIG.keys():
      self._antenna_service_strength[antenna] = dict()
    self._test_spec = dict()
    self.SwitchAntenna('all')
    self._antenna = 'all'
    self._space_event = threading.Event()
    self._done = threading.Event()

  def tearDown(self):
    """Restores antenna."""
    self.RestoreAntenna()

  def DetectPhyName(self):
    """Detects the phy name for device_name device.

    Returns:
      The phy name for device_name device.
    """
    output = CheckOutput(['iw', 'dev', self.args.device_name, 'info'])
    logging.info('info output: %s', output)
    number = GetProp(output, _RE_WIPHY, None)
    return ('phy' + number) if number else None

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
      strength = service_strengths[service]
      if strength:
        factory.console.info('Service %s signal strength %f.', service,
                             strength)
        Log('service_signal', service=service, strength=strength)
        if strength > max_strength:
          max_strength_service, max_strength = service, strength
      else:
        factory.console.info('Service %s has no signal strength.', service)

    if max_strength_service:
      logging.info('Service %s has the highest signal strength %f among %s.',
                   max_strength_service, max_strength, service_strengths)
      return max_strength_service
    else:
      logging.warning('Services %s are not available.', services)

  def ScanSignal(self, freq):
    """Scans signal on device.

    Args:
      freq: The frequency to scan.

    Returns:
      Scan output on device.
    """
    logging.info('Start scanning on %s freq %d.', self.args.device_name, freq)
    self._template.SetState(_MSG_SCANNING(self.args.device_name, freq))
    scan_output = IwScan(self.args.device_name, freq)
    self._template.SetState(_MSG_SCANNING_DONE(self.args.device_name, freq))
    logging.info('Scan finished.')
    return scan_output

  def ParseScanOutput(self, scan_output, service_mac):
    """Parses iw scan output to get ssid, freq and signal strength of service.

    This function can not parse two scan results with the same mac_address.

    Args:
      scan_output: iw scan output.
      service_mac: The service to scan.

    Returns:
      (ssid, freq, signal) if there is a unique service mac in the scan output.
      (None, None, None) otherwise.
    """
    ssid_freq_signal_list = []
    (mac, ssid, freq, signal) = (None, None, None, None)
    for line in scan_output.splitlines():
      line = line.strip()
      # a line starts with BSS should look like
      # BSS d8:c7:c8:b6:6b:50 (on wlan0)
      if line.startswith('BSS'):
        (mac, ssid, freq, signal) = (line.split()[1], None, None, None)
      freq = GetProp(line, _RE_FREQ, freq)
      signal = GetProp(line, _RE_SIGNAL, signal)
      ssid = GetProp(line, _RE_SSID, ssid)
      if freq and signal and ssid:
        if mac == service_mac:
          ssid_freq_signal_list.append((ssid, int(freq), float(signal)))
        (ssid, freq, signal) = (None, None, None)
    if len(ssid_freq_signal_list) == 1:
      return ssid_freq_signal_list[0]
    elif len(ssid_freq_signal_list) == 0:
      factory.console.warning('Can not scan service with mac %s.', service_mac)
      return (None, None, None)
    else:
      factory.console.warning('There are more than one results for mac %s.',
                              service_mac)
      for ssid, freq, signal in ssid_freq_signal_list:
        factory.console.warning('mac: %s, ssid: %s, freq: %d, signal %f',
                                service_mac, ssid, freq, signal)
      return (None, None, None)

  def SwitchAntenna(self, antenna):
    """Switches antenna.

    Args:
      antenna: The target antenna config. This should be one of the keys in
               _ANTENNA_CONFIG
    """
    tx_bitmap, rx_bitmap = _ANTENNA_CONFIG[antenna]
    IwSetAntenna(self.args.device_name, self._phy_name,
                 tx_bitmap, rx_bitmap,
                 switch_antenna_sleep_secs=self.args.switch_antenna_sleep_secs)
    self._antenna = antenna

  def RestoreAntenna(self):
    """Restores antenna config to 'all' if it is not 'all'."""
    if self._antenna == 'all':
      logging.info('Already using antenna "all".')
    else:
      logging.info('Restore antenna.')
      self._template.SetState(_MSG_SWITCHING_ANTENNA('all'))
      self.SwitchAntenna('all')

  def ScanAndAverageSignals(self, services, times=3):
    """Scans and averages signal strengths for services.

    Scans for specified times to get average signal strength.
    The dividend is the sum of signal strengths during all scans.
    The divisor is the number of times the service is in the scan result.
    If the service is not scannable during all scans, its value will be
    None.

    Args:
      services: A list of (service_mac, freq) tuples to scan.
      times: Number of times to scan to get average.

    Returns:
      A dict of average signal strength of each service in service.
    """
    # Gets all candidate freqs.
    set_all_freqs = set([service[1] for service in services])

    # keys are services and values are lists of each scannd value.
    scan_results = dict()
    for service in services:
      scan_results[service] = []

    for freq in sorted(set_all_freqs):
      # Scans for times
      for _ in xrange(times):
        scan_output = self.ScanSignal(freq)
        for service in services:
          service_mac = service[0]
          (ssid, freq_scanned, strength) = self.ParseScanOutput(scan_output,
                                                                service_mac)
          # strength may be 0.
          if strength is not None:
            # iw returns the scan results of other frequencies as well.
            if freq_scanned != freq:
              continue
            factory.console.info('scan : %s %s %d %f.', service_mac,
                                 ssid, freq_scanned, strength)
            scan_results[service].append(strength)

    # keys are services and values are averages
    average_results = dict()
    # Averages the scanned strengths
    for service, result in scan_results.iteritems():
      average_results[service] = (sum(result) / len(result)
                                  if len(result) else None)
    return average_results

  def SwitchAntennaAndScan(self, antenna):
    """Switches antenna and scans for services in self._test_spec.keys()

    Args:
      antenna: The antenna config to scan.
    """
    factory.console.info('Testing antenna %s.', antenna)
    self._template.SetState(_MSG_SWITCHING_ANTENNA(antenna))
    self.SwitchAntenna(antenna)
    self._antenna_service_strength[antenna] = self.ScanAndAverageSignals(
      self._test_spec.keys(), times=self.args.scan_count)
    factory.console.info(
        'Average scan result: %s.', self._antenna_service_strength[antenna])

  def CheckSpec(self, antenna):
    """Checks if the scan result of antenna config can meet test spec.

    Args:
      antenna: The antenna config to check.
    """
    factory.console.info('Checking antenna %s', antenna)
    scanned_service_strength = self._antenna_service_strength[antenna]
    for test_service, spec_antenna_strength in self._test_spec.iteritems():
      scanned_strength = scanned_service_strength[test_service]
      spec_strength = spec_antenna_strength[antenna]

      Log('antenna_%s' % antenna, freq=test_service[1],
          rssi=scanned_strength,
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
    set_all_antennas = set()
    for spec_services, spec_antenna_strength in self.args.spec_dict.iteritems():
      set_all_services = set_all_services.union(set(spec_services))
      set_all_antennas = set_all_antennas.union(
          set(spec_antenna_strength.keys()))

    logging.info('All candidate services: %s', set_all_services)
    logging.info('All required antenna configs: %s', set_all_antennas)

    # Scans using antenna 'all'.
    self._antenna_service_strength['all'] = self.ScanAndAverageSignals(
        set_all_services, self.args.scan_count)

    # Gets the service with the largest strength to test for each spec.
    for candidate_services, spec_strength in self.args.spec_dict.iteritems():
      test_service = self.ChooseMaxStrengthService(candidate_services,
          self._antenna_service_strength['all'])
      if test_service is None:
        self.fail('Services %s are not available.' % candidate_services)
      else:
        self._test_spec[test_service] = spec_strength

    # Checks 'all' since we have scanned using antenna 'all' already.
    self.CheckSpec('all')

    # Scans and tests for other antenna config.
    for antenna in set_all_antennas:
      if antenna == 'all':
        continue
      self.SwitchAntennaAndScan(antenna)
      self.CheckSpec(antenna)
