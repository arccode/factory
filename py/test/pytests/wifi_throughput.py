# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''WiFi throughput test.

Accepts a list of wireless services, checks for their signal strength, connects
to them, and tests data throughput rate using iperf.
'''

from __future__ import print_function

import csv
import logging
import os
import subprocess
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log, GetDeviceId
from cros.factory.system import SystemInfo
from cros.factory.system.service_manager import GetServiceStatus
from cros.factory.system.service_manager import SetServiceStatus
from cros.factory.system.service_manager import Status
from cros.factory.test import factory
from cros.factory.test import leds
from cros.factory.test.args import Arg
from cros.factory.test.fixture import arduino
from cros.factory.utils.net_utils import GetWLANInterface, GetWLANMACAddress
from cros.factory.utils.net_utils import SwitchEthernetInterfaces
from cros.factory.utils import process_utils

# pylint: disable=W0611, F0401
from cros.factory.test import autotest_common
from autotest_lib.client.cros.networking import wifi_proxy
# pylint: enable=W0611, F0401


_SERVICE_LIST = ['shill', 'shill_respawn', 'wpasupplicant', 'modemmanager']
_DEFAULT_TIMEOUT_SECS = 10


def retryWithTimeout(f, log_text=None, fail_text=None, timeout=None, sleep=1):
  '''Retries a call repeatedly, until non-False non-None output is returned.

  Args:
    f: Function to be called.  If arguments need to be sent to the function,
        the caller can wrap the call in a lambda.
    log_text: Text to pass to logging.info() before each attempt.
    fail_text: Text to use when raising an exception on timeout failure.  If
        none is given, we return False instead.
    timeout: Timeout in seconds after which we give up.
    sleep: Time in seconds to pause in between attempts.

  Returns:
    On success, f's non-False non-None return value.  On failure, False if
    fail_text is not provided.

  Raises:
    Exception if f doesn't succeed, and if fail_text is provided
  '''
  if timeout == None:
    timeout = _DEFAULT_TIMEOUT_SECS
  if timeout < 0:
    raise ValueError('Timeout must be >= 0')
  deadline = time.time() + timeout
  result = False
  while True:
    if log_text:
      logging.info("[%ds left] %s", deadline - time.time(), log_text)
    try:
      result = f()
    except Exception as e:
      logging.exception(e.message)
    if result != False and result != None:
      return result
    if time.time() >= deadline:
      break
    time.sleep(sleep)
  if fail_text:
    raise Exception(fail_text)
  return False


class WiFiThroughput(unittest.TestCase):
  ARGS = [
    Arg('event_log_name', str, 'Name of the event_log.  We might want to '
        're-run the throughput test at different points in the factory, so '
        'this can be used to separate them.  e.g. "rf_throughput_chamber"',
        optional=False),
    Arg('services', (list, tuple),
        'A list of WiFi services (ssid, password) tuple to test. '
        'e.g. [("ssid1", "password1"), ("ssid2", "password2")]. '
        'Set password to None or "" if it is an open network. '
        'If services are not specified, this test will check for any AP.',
        optional=True),
    Arg('min_signal_strength', int,
        'Minimum signal strength required (range from 0 to 100).',
        optional=True),
    Arg('iperf_host', str,
        'Host running iperf in server mode, used for testing data transmission '
        'speed.',
        optional=True, default=None),
    Arg('transmit_time', int,
        'Time in seconds for which to transmit data.',
        optional=True, default=10),
    Arg('transmit_interval', (int, float),
        'There will be an overall average of transmission speed.  But it may '
        'also be useful to check bandwidth within subintervals of this time. '
        'This argument can be used to check bandwidth for every interval of n '
        'seconds.  There will be floor(transmit_time / n) intervals, and any '
        'remaining time < transmit_time will not be independently reported.',
        optional=True, default=1),
    Arg('min_throughput', int,
        'Required minimum throughput in bits/sec.  If the average throughput '
        'is lower than this, we will fail.',
        optional=True, default=None),
    Arg('arduino_high_pins', list,
        'A list of ints.  If not None, set arduino pins in the list to high.',
        optional=True, default=None),
  ]

  def __init__(self, *args, **kwargs):
    super(WiFiThroughput, self).__init__(*args, **kwargs)

    self.leds_blinker = None

  def _Log(self):
    Log(self.args.event_log_name, **self.log)

  def _StartOperatorFeedback(self):
    # In case we're in a chamber without a monitor, start blinking keyboard LEDs
    # to inform the operator that we're still working.
    self.leds_blinker = leds.Blinker(
        [(0, 0.5), (leds.LED_NUM|leds.LED_CAP|leds.LED_SCR, 0.5)])
    self.leds_blinker.Start()

    # If arduino_high_pins is provided as an argument, then set the requested
    # pins in the list to high.
    if self.args.arduino_high_pins:
      arduino_controller = arduino.ArduinoDigitalPinController()
      arduino_controller.Connect()
      for high_pin in self.args.arduino_high_pins:
        arduino_controller.SetPin(high_pin)
      arduino_controller.Disconnect()

  def _EndOperatorFeedback(self):
    # Stop blinking LEDs.
    if self.leds_blinker:
      self.leds_blinker.Stop()

  def _RunBasicSSIDList(self):
    '''Basic WiFi test -- succeeds if it can see any AP.'''
    found_ssids = retryWithTimeout(
        self.wifi.get_active_wifi_SSIDs,
        log_text='Looking for WiFi services...',
        fail_text='Timed out while searching for WiFi services')
    return found_ssids

  def _ConnectToService(self, ssid, password):
    # Look for requested service.
    service = retryWithTimeout(
        lambda: self.wifi.find_matching_service({
          self.wifi.SERVICE_PROPERTY_TYPE: 'wifi',
          self.wifi.SERVICE_PROPERTY_NAME: ssid}),
        log_text='Looking for service %s...' % ssid,
        fail_text='Unable to find service %s' % ssid)

    # Check signal strength.
    if self.args.min_signal_strength is not None:
      strength = self.wifi.get_dbus_property(service, 'Strength')
      if strength >= self.args.min_signal_strength:
        factory.console.info('%s strength %d >= %d [pass]',
            ssid, strength, self.args.min_signal_strength)
      else:
        raise Exception('%s strength %d < %d [fail]' %
            (ssid, strength, self.args.min_signal_strength))

    # Check for connection state.
    is_active = self.wifi.get_dbus_property(service, 'IsActive')
    if is_active:
      raise Exception('Unexpectedly already connected to %s' % ssid)

    # Try connecting.
    logging.info('Connecting to %s...', ssid)
    security_dict = {
        self.wifi.SERVICE_PROPERTY_PASSPHRASE: password}
    (success, _, _, _, reason) = self.wifi.connect_to_wifi_network(
        ssid=ssid,
        security=('psk' if password else 'none'),
        security_parameters=(security_dict if password else {}),
        save_credentials=False,
        autoconnect=False)
    if not success:
      raise Exception('Unable to connect to %s: %s' % (ssid, reason))
    else:
      factory.console.info('Successfully connected to %s', ssid)
      return service

  def _RunIperfAndCheckOutput(self):
    '''Invokes an iperf client and parses throughput.

    This function uses the following data members:
      self.args.iperf_host: The host running an iperf server.
      self.args.transmit_time: Total time (seconds) to transmit data.
      self.args.transmit_interval: Time (seconds) of each sub-interval.

    Returns:
      Parsed CSV data output from iperf, as a list of dicts, where a[:-1] are
      for intervals and a[-1] is average.

    Raises:
      Exception on failure.
    '''
    logging.info('Running iperf connecting to host %s for %d seconds',
        self.args.iperf_host, self.args.transmit_time)

    # Invoke the iperf command.
    iperf_cmd = ['iperf',
        '--client', self.args.iperf_host,
        '--time', str(self.args.transmit_time),
        '--interval', str(self.args.transmit_interval),
        '--reportstyle', 'c']

    # We enclose the iperf call in timeout, since when given an unreachable
    # host, it seems to hang indefinitely.
    timeout_cmd = ['timeout',
        '--signal', 'KILL',
        # Add 5 seconds to allow for process overhead and connection time.
        str(self.args.transmit_time + 5)] + iperf_cmd
    iperf = process_utils.Spawn(timeout_cmd, stdout=subprocess.PIPE, log=True)

    # iperf outputs CSV with the following as its columns, with rows[:-1] for
    # intervals, and a[-1] for average values:
    column_names = [
        'timestamp',
        'source_address',
        'source_port',
        'destination_address',
        'destination_port',
        None,  # this field's purpose is unclear
        'interval',
        'transferred_bytes',
        'bits_per_second',
    ]

    # Turn iperf's output into a map based on the keys above.  Also, parse
    # integers.
    iperf_reader = csv.DictReader(
        iter(iperf.stdout.readline, ''),  # prevent output buffering
        fieldnames=column_names)
    iperf_dict = []
    for row in iperf_reader:
      # Parse any integers.
      parse_int_f = lambda v: int(v) if v.lstrip('-').isdigit() else v
      row = {k: parse_int_f(v) for k, v in row.iteritems()}
      # Filter out the 'None' row.
      del row[None]
      # Convert transferred_bytes to transferred_bits.
      row['transferred_bits'] = row['transferred_bytes'] * 8
      del row['transferred_bytes']
      logging.info('iperf output: %s', row)
      iperf_dict.append(row)

    # Ensure that there are least two rows.
    # Ensure for each row, transferred_bits > 0 and bits_per_second > 0.
    # If these conditions fail, we can assume iperf failed.
    if len(iperf_dict) < 2:
      raise Exception(
          'Failed to make a connection to iperf host %s, or received bogus '
          'output from iperf' % self.args.iperf_host)
    if (not all(row['transferred_bits'] > 0 for row in iperf_dict)
        or not all(row['bits_per_second'] > 0 for row in iperf_dict)):
      raise Exception(
          'Succeeded connnecting to %s, but received bogus output '
          'from iperf (transferred_bits or bits_per_second <= 0)' %
              self.args.iperf_host)

    def bitsToMbits(x):
      return x / (10.0 ** 6)

    factory.console.info(
        'Successfully connected to %s, transferred: %.2f Mbits, '
        'time spent: %d sec, throughput: %.2f Mbits/sec',
        self.args.iperf_host,
        bitsToMbits(iperf_dict[-1]['transferred_bits']),
        self.args.transmit_time,
        bitsToMbits(iperf_dict[-1]['bits_per_second']))

    if self.args.min_throughput is not None:
      # Ensure the average throughput is over the threshold.
      if iperf_dict[-1]['bits_per_second'] < self.args.min_throughput:
        raise Exception(
            'Throughput %.2f < %.2f Mbits/s didn\'t meet '
            'the threshold requirement' % (
                bitsToMbits(iperf_dict[-1]['bits_per_second']),
                bitsToMbits(self.args.min_throughput)))
    return iperf_dict

  def setUp(self):
    # Keyboard lights and arduino pins.
    self._StartOperatorFeedback()

    # Ensure all required services are enabled.
    for service in _SERVICE_LIST:
      if GetServiceStatus(service) == Status.STOP:
        SetServiceStatus(service, Status.START)

    # Initialize the log dict, which will later be fed into event log.
    system_info = SystemInfo()
    self.log = {
        'args': self.args,
        'run': {
            'path': os.environ.get('CROS_FACTORY_TEST_PATH'),
            'invocation': os.environ.get('CROS_FACTORY_TEST_INVOCATION')},
        'dut': {
            'device_id': GetDeviceId(),
            'mac_address': GetWLANMACAddress(),
            'serial_number': system_info.serial_number,
            'mlb_serial_number': system_info.mlb_serial_number},
        'ssid_list': {},
        'test': {},
        'failures': []}

    # Initialize our WifiProxy library.
    self.wifi = wifi_proxy.WifiProxy()

    # Since in some test set-ups, the ethernet interface will be on the same
    # subnet as the wireless interface, we need to first disable ethernet to
    # avoid the throughput test being routed through a wired connection.
    # TODO(kitching): Change the network topology of tests with this problem so
    # that we don't have to take down ethernet.  This way, goofy-split won't
    # disconnect its display when the test is run.
    logging.info('Disabling ethernet interfaces')
    SwitchEthernetInterfaces(False)

  def tearDown(self):
    self._EndOperatorFeedback()

    # Enable ethernet devices.
    SwitchEthernetInterfaces(True)

  def _RunTestChecks(self):
    # Check that we have an online WLAN interface.
    dev = GetWLANInterface()
    if not dev:
      error_str = 'No wireless interface available'
      self.log['failures'].append(error_str)
      self._Log()
      self.fail(error_str)
    else:
      logging.info('ifconfig %s up', dev)
      process_utils.Spawn(['ifconfig', dev, 'up'], check_call=True, log=True)

    # Ensure that WiFi is in a disconnected state.
    service = self.wifi.find_matching_service({
        self.wifi.SERVICE_PROPERTY_TYPE: 'wifi',
        'IsActive': True})
    if service:
      logging.info('First disconnect from current WiFi service...')
      if not self.wifi.disconnect_service_synchronous(
          service, _DEFAULT_TIMEOUT_SECS):
        error_str = 'Failed to disconnect from current WiFi service'
        self.log['failures'].append(error_str)
        self._Log()
        self.fail(error_str)
      else:
        logging.info('Disconnected successfully from current WiFi service')

    # Manually request a scan of WiFi services.
    self.wifi.manager.RequestScan('wifi')

  def runTest(self):
    self._RunTestChecks()

    # Run a basic SSID list test.
    found_ssids = self._RunBasicSSIDList()
    if found_ssids:
      factory.console.info('Found services: %s', ', '.join(found_ssids))
      self.log['ssid_list'] = found_ssids
    else:
      logging.info('No services found')

    if self.args.services:
      # Test WiFi signal strength for each service.
      if not isinstance(self.args.services, list):
        self.args.services = [self.args.services]

      # Set up log data structure.
      for ssid, password in self.args.services:
        self._RunOneServiceCheck(ssid, password)

    # Log this test run.
    self._Log()

    # Check for any failures in connecting.
    all_failures_str = []
    for ssid, log in self.log['test'].iteritems():
      for error_msg in log['failures']:
        all_failures_str.append("* [%s] %s" % (ssid, error_msg))
    if all_failures_str:
      error_msg = ('Error in connecting and running iperf '
                   'on one or more services')
      factory.console.info('%s:\n%s', error_msg, '\n'.join(all_failures_str))
      self.fail(error_msg)

  def _RunOneServiceCheck(self, ssid, password):
    # Set up logging dict.
    self.log['test'][ssid] = {
        'ifconfig': None,
        'iwconfig': None,
        'ap': None,
        'iperf': None,
        'failures': []}

    # Try connecting.
    try:
      factory.console.info('Trying to connect to service %s...', ssid)
      service = self._ConnectToService(ssid, password)
    except Exception as e:
      self.log['test'][ssid]['failures'].append(e.message)
      factory.console.info('Failed connecting to service %s', ssid)
      logging.exception(e.message)
      return

    # Show ifconfig and iwconfig output.
    self.log['test'][ssid]['ifconfig'] = process_utils.SpawnOutput(['ifconfig'],
        check_call=True, log=True)
    logging.info(self.log['test'][ssid]['ifconfig'])
    self.log['test'][ssid]['iwconfig'] = process_utils.SpawnOutput(['iwconfig'],
        check_call=True, log=True)
    logging.info(self.log['test'][ssid]['iwconfig'])

    # Save network ssid details.
    self.log['test'][ssid]['ap'] = {
        'ssid': self.wifi.get_dbus_property(service, 'Name'),
        'security': self.wifi.get_dbus_property(service, 'Security'),
        'strength': self.wifi.get_dbus_property(service, 'Strength'),
        'bssid': self.wifi.get_dbus_property(service, 'WiFi.BSSID'),
        'frequency': self.wifi.get_dbus_property(service, 'WiFi.Frequency')}

    # Try to test throughput with iperf if requested.
    if self.args.iperf_host is not None:
      try:
        factory.console.info('Trying to run iperf on host %s...',
            self.args.iperf_host)
        self.log['test'][ssid]['iperf'] = self._RunIperfAndCheckOutput()
      except Exception as e:
        self.log['test'][ssid]['failures'].append(e.message)
        factory.console.info('Ran iperf on host %s with error: %s',
            self.args.iperf_host, e.message)
        logging.exception(e.message)

    # Finally, disconnect from this network.
    if not self.wifi.disconnect_service_synchronous(
        service, _DEFAULT_TIMEOUT_SECS):
      error_str = 'Failed to disconnect from %s' % ssid
      self.log['test'][ssid]['failures'].append(error_str)
      logging.info(error_str)
    else:
      logging.info('Disconnected successfully from %s', ssid)

    # Return success status.
    return self.log['test'][ssid]['failures'] == []
