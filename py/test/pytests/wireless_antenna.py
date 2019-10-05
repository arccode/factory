# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for basic Wifi.

Description
-----------
The test checks if the strength of the input wireless services list satisfy the
input spec via "iw dev {device} scan".

Be sure to set AP correctly.
1. Select a fixed channel instead of auto.
2. Disable the power control in AP.
3. Make sure SSID of AP is unique.

Test Procedure
--------------
The test accepts a dict of wireless specs.
Each spec contains candidate services and the signal constraints.
For each spec, the test will first scan the signal quality using 'all' antenna
to determine the strongest service to test. Then the test switches antenna
configuration to test signal quality.

Dependency
----------
- `iw` utility
- `ifconfig` utility

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

from __future__ import print_function

import logging
import subprocess
import sys

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


# The scanned result with last_seen value greater than this value
# will be ignored.
_THRESHOLD_LAST_SEEN_MS = 1000


class IwException(Exception):
  pass

def IwSetAntenna(dut, devname, phyname, tx_bitmap, rx_bitmap, max_retries=10,
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
  dut.wifi.BringsDownInterface(devname)
  try_count = 0
  success = False
  while try_count < max_retries:
    process = dut.Popen(
        ['iw', 'phy', phyname, 'set', 'antenna', tx_bitmap, rx_bitmap],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, log=True)
    unused_stdout, stderr = process.communicate()
    retcode = process.returncode
    if retcode == 0:
      success = True
      break
    # (-95) EOPNOTSUPP Operation not supported on transport endpoint
    # Do ifconfig down again may solve this problem.
    elif retcode == 161:
      try_count += 1
      session.console.info('Retry...')
      dut.wifi.BringsDownInterface(devname)
    else:
      raise IwException('Failed to set antenna. ret code: %d. stderr: %s' %
                        (retcode, stderr))
  dut.wifi.BringsUpInterface(devname, switch_antenna_sleep_secs)
  if not success:
    raise IwException('Failed to set antenna for %s tries' % max_retries)


_ANTENNA_CONFIG = {'main': ('1', '1'),
                   'aux': ('2', '2'),
                   'all': ('3', '3')}


class WirelessTest(test_case.TestCase):
  """Basic wireless test class.

  Properties:
    _antenna: current antenna config.
    _phy_name: wireless phy name to test.
    _antenna_service_strength: a dict of dict to store the scan result
        of each service under each antenna config. e.g.
        {'all':{'AP1': -30, 'AP2': -40},
         'main': {'AP1': -40, 'AP2': -50},
         'aux': {'AP1': -40, 'AP2': -50}}
  """
  ARGS = [
      Arg('device_name', str,
          'Wireless device name to test. e.g. wlan0. If not specified, it will'
          'fail if multiple devices are found, otherwise use the only one '
          'device it found.', default=None),
      Arg('services', list,
          'A list of (service_ssid, freq, password) tuples like '
          '``[(SSID1, FREQ1, PASS1), (SSID2, FREQ2, PASS2), '
          '(SSID3, FREQ3, PASS3)]``. The test will only check the service '
          'whose antenna_all signal strength is the largest. For example, if '
          '(SSID1, FREQ1, PASS1) has the largest signal among the APs, '
          'then only its results will be checked against the spec values.'),
      Arg('strength', dict,
          'A dict of minimal signal strengths. For example, a dict like '
          '``{"main": strength_1, "aux": strength_2, "all": strength_all}``. '
          'The test will check signal strength according to the different '
          'antenna configurations in this dict.'),
      Arg('scan_count', int,
          'Number of scans to get average signal strength.', default=5),
      Arg('switch_antenna_sleep_secs', int,
          'The sleep time after switchingantenna and ifconfig up. Need to '
          'decide this value carefully since it depends on the platform and '
          'antenna config to test.', default=10),
      Arg('disable_switch', bool,
          'Do not switch antenna, just check "all" '
          'config.', default=False),
      Arg('press_space_to_start', bool,
          'Press space to start the test.', default=True)]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)

    self._dut = device_utils.CreateDUTInterface()
    self._device_name = None
    self._phy_name = None
    self._antenna = None
    self._services = [wifi.ServiceSpec(ssid, freq, password)
                      for ssid, freq, password in self.args.services]
    self.assertTrue(self._services, 'At least one service should be specified.')
    self._antenna_service_strength = {}
    for antenna in _ANTENNA_CONFIG:
      self._antenna_service_strength[antenna] = {}

    if self.args.disable_switch and list(self.args.strength) != ['all']:
      self.fail('Switching antenna is disabled but antenna configs are %s' %
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
    """Restores antenna."""
    self.RestoreAntenna()

  def _ChooseMaxStrengthService(self):
    """Chooses the service that has the largest signal strength among services.

    Returns:
      The service that has the largest signal strength among services.
    """
    max_strength_service, max_strength = None, -sys.float_info.max
    for service in self._services:
      strength = self._GetAverageSignal(service, 'all')
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

  def ScanSignal(self, freq):
    """Scans signal on device.

    Args:
      freq: The frequency to scan.

    Returns:
      Scan output on device.
    """
    logging.info('Start scanning on %s freq %d.', self._device_name, freq)
    self.ui.SetState(
        _('Scanning on device {device} frequency {freq}...',
          device=self._device_name,
          freq=freq))

    scan_output = self._dut.wifi.FilterAccessPoints(interface=self._device_name,
                                                    frequency=freq)

    self.ui.SetState(
        _('Done scanning on device {device} frequency {freq}...',
          device=self._device_name,
          freq=freq))
    logging.info('Scan finished.')
    return scan_output

  def ParseScanOutput(self, scan_output, service_ssid, service_freq):
    """Select iw scan output to get a service that matches constraints.

    If there are multiple choses, return the one with strongest signal.

    Args:
      scan_output: iw scan output.
      service_ssid: The ssid of the service to scan.
      service_freq: The frequency of the service to scan.

    Returns:
      An wifi.AccessPoint object.
    """
    parsed_tuples = []
    for ap in scan_output:
      if (ap.ssid == service_ssid and
          ap.frequency == service_freq and
          ap.last_seen <= _THRESHOLD_LAST_SEEN_MS):
        parsed_tuples.append(ap)

    if not parsed_tuples:
      session.console.warning('Can not scan service %s.', service_ssid)
      return None
    if len(parsed_tuples) > 1:
      session.console.warning('There are more than one result for ssid %s.',
                              service_ssid)
      for ap in parsed_tuples:
        session.console.warning(
            'mac: %s, ssid: %s, freq: %d, signal %f, last_seen %d ms',
            ap.bssid, ap.ssid, ap.frequency, ap.strength, ap.last_seen)
    # Return the one with strongest signal.
    return max(parsed_tuples, key=lambda t: t.strength)

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
      self._dut.wifi.BringsUpInterface(self._device_name,
                                       self.args.switch_antenna_sleep_secs)
      return
    tx_bitmap, rx_bitmap = _ANTENNA_CONFIG[antenna]
    IwSetAntenna(self._dut, self._device_name, self._phy_name,
                 tx_bitmap, rx_bitmap,
                 switch_antenna_sleep_secs=self.args.switch_antenna_sleep_secs)
    self._antenna = antenna

  def RestoreAntenna(self):
    """Restores antenna config to 'all' if it is not 'all'."""
    if self._antenna == 'all':
      logging.info('Already using antenna "all".')
    else:
      logging.info('Restore antenna.')
      self.SwitchAntenna('all')

  def _ScanSignals(self, services, antenna):
    """Scans and averages signal strengths for services.

    Scans for specified times to get average signal strength.
    The dividend is the sum of signal strengths during all scans.
    The divisor is the number of times the service is in the scan result.
    If the service is not scannable during all scans, its value will be
    None.

    Args:
      services: A list of (service_ssid, freq) tuples to scan.
      antenna: The antenna config to scan.
    """
    session.console.info('Testing antenna %s.', antenna)
    self.ui.SetState(_('Switching to antenna {antenna}: ', antenna=antenna))
    self.SwitchAntenna(antenna)

    # Gets all candidate freqs.
    set_all_freqs = set([service.freq for service in services])

    # keys are services and values are lists of each scanned value.
    scan_results = {}
    for service in services:
      scan_results[service] = []

    for freq in sorted(set_all_freqs):
      # Scans for times
      for unused_i in xrange(self.args.scan_count):
        scan_output = self.ScanSignal(freq)
        for service in services:
          if service.freq != freq:
            continue
          ap = self.ParseScanOutput(scan_output, service.ssid, service.freq)
          if ap is not None:
            session.console.info(
                'scan : %s %s %d %f %d ms.', ap.ssid, ap.bssid, ap.frequency,
                ap.strength, ap.last_seen)
            scan_results[service].append(ap.strength)

    # keys are services and values are averages
    average_results = {}
    # Averages the scanned strengths
    for service, result in scan_results.iteritems():
      average_results[service] = (sum(result) / len(result) if result else None)
    self._antenna_service_strength[antenna] = average_results
    session.console.info(
        'Average scan result: %s.', self._antenna_service_strength[antenna])

  def _GetAverageSignal(self, service, antenna):
    return self._antenna_service_strength[antenna][service]

  def _CheckSpec(self, service, spec_antenna_strength, antenna):
    """Checks if the scan result of antenna config can meet test spec.

    Args:
      service: (service_ssid, freq, password) tuple.
      spec_antenna_strength: A dict of minimal signal strengths.
      antenna: The antenna config to check.
    """
    session.console.info('Checking antenna %s spec', antenna)
    scanned_strength = self._GetAverageSignal(service, antenna)
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

  def _ScanAllServices(self):
    self.ui.SetState(_('Checking frequencies...'))

    scan_result = self._dut.wifi.FilterAccessPoints(interface=self._device_name)
    ssid_freqs = {service.ssid: set() for service in self._services}

    for scanned_service in scan_result:
      if scanned_service.ssid in ssid_freqs:
        ssid_freqs[scanned_service.ssid].add(scanned_service.frequency)

    for service in self._services:
      if not ssid_freqs[service.ssid]:
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
