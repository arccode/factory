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
3. Make sure SSID of AP is unique.
"""

from __future__ import print_function
import logging
import re
import sys
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

_DEFAULT_WIRELESS_TEST_CSS = '.wireless-info {font-size: 2em;}'

_MSG_SWITCHING_ANTENNA = lambda antenna: i18n_test_ui.MakeI18nLabelWithClass(
    'Switching to antenna {antenna}: ', 'wireless-info', antenna=antenna)
_MSG_SCANNING = lambda device, freq: i18n_test_ui.MakeI18nLabelWithClass(
    'Scanning on device {device} frequency {freq}...',
    'wireless-info',
    device=device,
    freq=freq)
_MSG_SCANNING_DONE = lambda device, freq: i18n_test_ui.MakeI18nLabelWithClass(
    'Done scanning on device {device} frequency {freq}...',
    'wireless-info',
    device=device,
    freq=freq)
_MSG_SPACE = i18n_test_ui.MakeI18nLabelWithClass(
    'Press space to start scanning.', 'wireless-info')

_RE_FREQ = re.compile(r'^freq: ([\d]*?)$')
_RE_SIGNAL = re.compile(r'^signal: ([-\d.]*?) dBm')
_RE_SSID = re.compile(r'^SSID: ([-\w]*)$')
_RE_LAST_SEEN = re.compile(r'^last seen: ([\d]+) ms ago$')
_RE_WIPHY = re.compile(r'wiphy (\d+)')

# The scanned result with last_seen value greater than this value
# will be neglected.
_THRESHOLD_LAST_SEEN_MS = 1000


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
  process_utils.Spawn(['ifconfig', devname, 'up'], check_call=True, log=True)
  # Wait for device to settle down.
  time.sleep(sleep_time_secs)


def IfconfigDown(devname, sleep_time_secs=1):
  """Brings down interface.

  Args:
    devname: Device name.
    sleep_time_secs: The sleeping time after ifconfig down.
  """
  process_utils.Spawn(['ifconfig', devname, 'down'], check_call=True, log=True)
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
    process = process_utils.Spawn(
        ['iw', 'phy', phyname, 'set', 'antenna', tx_bitmap, rx_bitmap],
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
    process = process_utils.Spawn(
        cmd, read_stdout=True, log_stderr_on_error=True, log=True)
    stdout, stderr = process.communicate()
    retcode = process.returncode
    event_log.Log('iw_scaned', retcode=retcode, stderr=stderr)
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
    _space_event: An event that space has been pressed. It will also be set
        if test has been done.
    _done: An event that test has been done.
  """
  ARGS = [
      Arg('device_name', str,
          'Wireless device name to test. '
          'Set this correctly if check_antenna is True.', default='wlan0'),
      Arg('services', list,
          'A list of (service_ssid, freq) tuples like '
          '``[(SSID1, FREQ1), (SSID2, FREQ2), '
          '(SSID3, FREQ3)]``. The test will only check the service '
          'whose antenna_all signal strength is the largest. For example, if '
          '(SSID1, FREQ1) has the largest signal among the APs, '
          'then only its results will be checked against the spec values.',
          optional=False),
      Arg('strength', dict,
          'A dict of minimal signal strengths. For example, a dict like '
          '``{"main": strength_1, "aux": strength_2, "all": strength_all}``. '
          'The test will check signal strength according to the different '
          'antenna configurations in this dict.',
          optional=False),
      Arg('scan_count', int,
          'Number of scans to get average signal strength.', default=5),
      Arg('switch_antenna_sleep_secs', int,
          'The sleep time after switchingantenna and ifconfig up. Need to '
          'decide this value carefully since itdepends on the platform and '
          'antenna config to test.', default=10),
      Arg('disable_switch', bool,
          'Do not switch antenna, just check "all" '
          'config.', default=False)]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._ui.AppendCSS(_DEFAULT_WIRELESS_TEST_CSS)
    self._phy_name = self.DetectPhyName()
    logging.info('phy name is %s.', self._phy_name)
    self._antenna_service_strength = {}
    for antenna in _ANTENNA_CONFIG.keys():
      self._antenna_service_strength[antenna] = {}
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
    output = process_utils.CheckOutput(
        ['iw', 'dev', self.args.device_name, 'info'])
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
        event_log.Log('service_signal', service=service, strength=strength)
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

  def ParseScanOutput(self, scan_output, service_ssid):
    """Parses iw scan output to get mac, freq and signal strength of service.

    This function can not parse two scan results with the same service_ssid.

    Args:
      scan_output: iw scan output.
      service_ssid: The ssid of the service to scan.

    Returns:
      (mac, freq, signal, last_seen) if there is a scan result of ssid in
        the scan_output. last_seen is in ms.
      (None, None, None, None) otherwise.
    """
    parsed_tuples = []
    (mac, ssid, freq, signal, last_seen) = (None, None, None, None, None)
    for line in scan_output.splitlines():
      line = line.strip()
      # a line starts with BSS should look like
      # BSS d8:c7:c8:b6:6b:50(on wlan0)
      if line.startswith('BSS'):
        bss_format_line = re.sub(r'[ ()]', ' ', line)
        (mac, ssid, freq, signal, last_seen) = (
            bss_format_line.split()[1], None, None, None, None)
      freq = GetProp(line, _RE_FREQ, freq)
      signal = GetProp(line, _RE_SIGNAL, signal)
      ssid = GetProp(line, _RE_SSID, ssid)
      last_seen = GetProp(line, _RE_LAST_SEEN, last_seen)
      if mac and freq and signal and ssid and last_seen:
        if ssid == service_ssid:
          parsed_tuples.append(
              (mac, int(freq), float(signal), int(last_seen)))
        (mac, ssid, freq, signal, last_seen) = (None, None, None, None, None)
    if len(parsed_tuples) == 1:
      return parsed_tuples[0]
    elif len(parsed_tuples) == 0:
      factory.console.warning('Can not scan service %s.', service_ssid)
      return (None, None, None, None)
    else:
      factory.console.warning('There are more than one results for ssid %s.',
                              service_ssid)
      for mac, freq, signal, last_seen in parsed_tuples:
        factory.console.warning(
            'mac: %s, ssid: %s, freq: %d, signal %f, '
            'last_seen %d ms', mac, service_ssid, freq, signal, last_seen)
      return (None, None, None, None)

  def SwitchAntenna(self, antenna):
    """Switches antenna.

    Args:
      antenna: The target antenna config. This should be one of the keys in
               _ANTENNA_CONFIG
    """
    if self.args.disable_switch:
      logging.info('Switching antenna is disabled. Skipping setting antenna to'
                   ' %s. Just bring up the interface.', antenna)
      # Bring up the interface because IwSetAntenna brings up interface after
      # antenna is switched.
      IfconfigUp(self.args.device_name, self.args.switch_antenna_sleep_secs)
      return
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
      services: A list of (service_ssid, freq) tuples to scan.
      times: Number of times to scan to get average.

    Returns:
      A dict of average signal strength of each service in service.
    """
    # Gets all candidate freqs.
    set_all_freqs = set([service[1] for service in services])

    # keys are services and values are lists of each scannd value.
    scan_results = {}
    for service in services:
      scan_results[service] = []

    for freq in sorted(set_all_freqs):
      # Scans for times
      for _ in xrange(times):
        scan_output = self.ScanSignal(freq)
        for service in services:
          service_ssid = service[0]
          (mac, freq_scanned, strength, last_seen) = self.ParseScanOutput(
              scan_output, service_ssid)
          if last_seen > _THRESHOLD_LAST_SEEN_MS:
            logging.warning('Neglect cached scan : %s %d ms ago.',
                            service_ssid, last_seen)
            continue
          # strength may be 0.
          if strength is not None:
            # iw returns the scan results of other frequencies as well.
            if freq_scanned != freq:
              continue
            factory.console.info(
                'scan : %s %s %d %f %d ms.', service_ssid, mac, freq_scanned,
                strength, last_seen)
            scan_results[service].append(strength)

    # keys are services and values are averages
    average_results = {}
    # Averages the scanned strengths
    for service, result in scan_results.iteritems():
      average_results[service] = (sum(result) / len(result)
                                  if len(result) else None)
    return average_results

  def SwitchAntennaAndScan(self, services, antenna):
    """Switches antenna and scans for all services.

    Args:
      services: A list of (service_ssid, freq) tuples to scan.
      antenna: The antenna config to scan.
    """
    factory.console.info('Testing antenna %s.', antenna)
    self._template.SetState(_MSG_SWITCHING_ANTENNA(antenna))
    self.SwitchAntenna(antenna)
    self._antenna_service_strength[antenna] = self.ScanAndAverageSignals(
        services, times=self.args.scan_count)
    factory.console.info(
        'Average scan result: %s.', self._antenna_service_strength[antenna])

  def CheckSpec(self, service, spec_antenna_strength, antenna):
    """Checks if the scan result of antenna config can meet test spec.

    Args:
      service: (service_ssid, freq) tuple.
      spec_antenna_strength: A dict of minimal signal strengths.
      antenna: The antenna config to check.
    """
    factory.console.info('Checking antenna %s spec', antenna)
    scanned_service_strength = self._antenna_service_strength[antenna]
    scanned_strength = scanned_service_strength[service]
    spec_strength = spec_antenna_strength[antenna]

    event_log.Log('antenna_%s' % antenna, freq=service[1],
                  rssi=scanned_strength,
                  meet=(scanned_strength and scanned_strength > spec_strength))
    if not scanned_strength:
      self.fail(
          'Antenna %s, service: %s: Can not scan signal strength.' %
          (antenna, service))
    if scanned_strength < spec_strength:
      self.fail(
          'Antenna %s, service: %s: The scanned strength %f < spec strength'
          ' %f' % (antenna, service, scanned_strength, spec_strength))
    else:
      factory.console.info(
          'Antenna %s, service: %s: The scanned strength %f > spec strength'
          ' %f', antenna, service, scanned_strength, spec_strength)

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
    self._template.SetState(_MSG_SPACE)
    self._ui.BindKey(test_ui.SPACE_KEY,
                     lambda _: self.OnSpacePressed(),
                     once=True)
    self._ui.RunInBackground(self._runTest)
    self._ui.Run(on_finish=self.Done)

  def _runTest(self):
    self._space_event.wait()
    if self._done.isSet():
      return

    if self.args.disable_switch and self.args.strength.keys() != ['all']:
      self.fail('Switching antenna is disabled but antenna configs are %s' %
                self.args.strength.keys())

    # Scans using antenna 'all'.
    self._antenna_service_strength['all'] = self.ScanAndAverageSignals(
        self.args.services, self.args.scan_count)

    # Gets the service with the largest strength to test for each spec.
    test_service = self.ChooseMaxStrengthService(
        self.args.services, self._antenna_service_strength['all'])
    if test_service is None:
      self.fail('Services %s are not valid.' % self.args.services)

    # Checks 'all' since we have scanned using antenna 'all' already.
    self.CheckSpec(test_service, self.args.strength, 'all')

    # Scans and tests for other antenna config.
    for antenna in self.args.strength:
      if antenna == 'all':
        continue
      self.SwitchAntennaAndScan(self.args.services, antenna)
      self.CheckSpec(test_service, self.args.strength, antenna)
