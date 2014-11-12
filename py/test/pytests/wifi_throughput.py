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
from cros.factory.test.args import Arg, Args
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
_IPERF_LOCAL_SERVER_PORT = 5050


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
  # Arguments that can only be applied to each WiFi service connection.  These
  # will be checked as key-values in the test's "service" argument (see below).
  _SERVICE_ARGS = [
      Arg('ssid', str,
          'SSID of WiFi service.',
          optional=False),
      Arg('password', str,
          'Password of WiFi service.',
          optional=True, default=None)
  ]

  # Arguments that can be directly applied to each WiFi service connection, OR
  # directly provided as a test argument.  "service" arguments take precedence.
  # e.g.
  #   test arg: min_signal_strength=50
  #   service A arg: min_signal_strength=40
  #   service B arg: [doesn't provide min_signal_strength]
  # result:
  #   service A min_signal_strength=40
  #   service B min_signal_strength=50
  _SHARED_ARGS = [
      Arg('min_signal_strength', int,
          'Minimum signal strength required (range from 0 to 100).',
          optional=True),
      Arg('iperf_host', str,
          'Host running iperf in server mode, used for testing data '
          'transmission speed.',
          optional=True, default=None),
      Arg('transmit_time', int,
          'Time in seconds for which to transmit data.',
          optional=True, default=10),
      Arg('transmit_interval', (int, float),
          'There will be an overall average of transmission speed.  But it may '
          'also be useful to check bandwidth within subintervals of this time. '
          'This argument can be used to check bandwidth for every interval of '
          'n seconds.  There will be floor(transmit_time / n) intervals, and '
          'any remaining time < transmit_time will not be independently '
          'reported.',
          optional=True, default=1),
      Arg('min_rx_throughput', int,
          'Required host-to-DUT (RX) minimum throughput in Mbits/sec.  If the '
          'average throughput is lower than this, we will fail.',
          optional=True, default=None),
      Arg('min_tx_throughput', int,
          'Required host-to-DUT (TX) minimum throughput in Mbits/sec.  If the '
          'average throughput is lower than this, we will fail.',
          optional=True, default=None),
  ]

  # Test-level arguments.  _SHARED_ARGS is concatenated at the end, since we
  # want the option to provide arguments as global defaults (as in the example
  # above).
  ARGS = [
      Arg('event_log_name', str, 'Name of the event_log.  We might want to '
          're-run the conductive test at different points in the factory, so '
          'this can be used to separate them.  '
          'e.g. "wifi_throughput_in_chamber"',
          optional=False),
      Arg('arduino_high_pins', list,
          'A list of ints.  If not None, set arduino pins in the list to high.',
          optional=True, default=None),
      Arg('disable_eth', bool,
          'Whether we should take down the ethernet device during this test.',
          optional=True, default=False),
      Arg('services', (list, dict),
          'A list of dicts, each representing a WiFi service to test.  At '
          'minimum, each must have a "ssid" field.  Usually, a "password" '
          'field is also included.  (Omit or set to None or "" for an open '
          'network.)  Additionally, the following fields can be provided to '
          'override arguments passed to this test (refer to _SHARED_ARGS): '
          'min_signal_strength, iperf_host, transmit_time, transmit_interval, '
          'min_rx_throughput, min_tx_throughput.  If services are not '
          'specified, this test will simply list APs.  Also note that each '
          'service may only be specified once.',
          optional=True, default=[]),
  ] + _SHARED_ARGS

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

  def _ConnectToService(self, ssid, password, min_signal_strength):
    # Look for requested service.
    service = retryWithTimeout(
        lambda: self.wifi.find_matching_service({
          self.wifi.SERVICE_PROPERTY_TYPE: 'wifi',
          self.wifi.SERVICE_PROPERTY_NAME: ssid}),
        log_text='Looking for service %s...' % ssid,
        fail_text='Unable to find service %s' % ssid)

    # Check signal strength.
    if min_signal_strength is not None:
      strength = self.wifi.get_dbus_property(service, 'Strength')
      if strength >= min_signal_strength:
        factory.console.info('%s strength %d >= %d [pass]',
            ssid, strength, min_signal_strength)
      else:
        raise Exception('%s strength %d < %d [fail]' %
            (ssid, strength, min_signal_strength))

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

  def _RunIperfAndCheckOutput(self, iperf_host, transmit_time,
      transmit_interval, min_rx_throughput, min_tx_throughput):
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
        iperf_host, transmit_time)

    # First, punch a hole through the firewall for incoming connections of the
    # bidirectional test (host connects to DUT).
    def IPTablesOpenPort(is_add=True, port=_IPERF_LOCAL_SERVER_PORT):
      process_utils.Spawn(['iptables',
          '-A' if is_add else '-D', 'INPUT',
          '-p', 'tcp', '--dport', str(port), '-j', 'ACCEPT'], log=True)
    IPTablesOpenPort(True)

    # Invoke the iperf command.
    iperf_cmd = ['iperf',
        '--client', iperf_host,
        '--dualtest',  # bidirectional test
        '--listenport', str(_IPERF_LOCAL_SERVER_PORT),
        '--time', str(transmit_time),
        '--interval', str(transmit_interval),
        '--reportstyle', 'c']

    # We enclose the iperf call in timeout, since when given an unreachable
    # host, it seems to hang indefinitely.
    timeout_cmd = ['timeout',
        '--signal', 'KILL',
        # Add 5 seconds to allow for process overhead and connection time.
        str(transmit_time + 5)] + iperf_cmd
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
    # TODO(kitching): Note that in the current version of iperf (2.0.4), there
    # is a bug which results in all RX transferred_bytes and bits_per_second
    # being erroneously returned as 0.  If this version of wifi_throughput is
    # used, iperf must first be upgraded for valid results.
    iperf_reader = csv.DictReader(
        iter(iperf.stdout.readline, ''),  # prevent output buffering
        fieldnames=column_names)
    iperf_rx = []
    iperf_tx = []
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

      # Separate bidirectionality for rx and tx.
      # source_port == (--listenport value) iff rx row
      if row['source_port'] == _IPERF_LOCAL_SERVER_PORT:
        iperf_rx.append(row)
      else:
        iperf_tx.append(row)

    # Delete the iptables rule we created for bidirectional testing.
    IPTablesOpenPort(False)

    # Ensure that there are least two rows.
    # Ensure for each row, transferred_bits > 0 and bits_per_second > 0.
    # If these conditions fail, we can assume iperf failed.
    if len(iperf_tx) < 2:
      raise Exception(
          'Failed to make a connection to iperf host %s, or received bogus '
          'output from iperf' % iperf_host)
    if len(iperf_rx) < 2:
      raise Exception(
          'DUT-to-host iperf succeeded, but host-to-DUT iperf connection '
          'failed for host %s; likely a problem with iptables' % iperf_host)
    iperf_both = iperf_rx + iperf_tx
    if (not all(row['transferred_bits'] > 0 for row in iperf_both)
        or not all(row['transferred_bits'] > 0 for row in iperf_both)):
      raise Exception(
          'Succeeded connnecting to %s, but received bogus output '
          'from iperf (transferred_bits or bits_per_second <= 0)' %
              iperf_host)

    # Check throughput to make sure it meets the minimum.  If it doesn't, then
    # we should add to the list of failures!
    failures = []
    def check_throughput(name, iperf_avg, min_throughput):
      def bitsToMbits(x):
        return x / (10.0 ** 6)

      factory.console.info('%s transferred: %.2f Mbits, '
          'time spent: %d sec, throughput: %.2f Mbits/sec',
          name,
          bitsToMbits(iperf_avg['transferred_bits']),
          transmit_time,
          bitsToMbits(iperf_avg['bits_per_second']))
      if min_throughput is not None:
        # Ensure the average throughputs are over their respective thresholds.
        if bitsToMbits(iperf_avg['bits_per_second']) < min_throughput:
          failures.append(
              '%s throughput %.2f < %.2f Mbits/s didn\'t meet '
              'the threshold requirement' % (
                  name,
                  bitsToMbits(iperf_avg['bits_per_second']),
                  min_throughput))

    # Last row is aggregate/average.
    factory.console.info('Successfully connected to %s', iperf_host)
    check_throughput('RX', iperf_rx[-1], min_rx_throughput)
    check_throughput('TX', iperf_tx[-1], min_tx_throughput)

    return {
        'iperf_rx': iperf_rx,
        'iperf_tx': iperf_tx,
        'failures': failures}

  def setUp(self):
    # Ensure that each service SSID is only specified once.
    ssids = [service['ssid'] for service in self.args.services]
    if len(ssids) != len(set(ssids)):
      raise ValueError("['services'] argument may only specify each SSID once")

    # Initialize the log dict, which will later be fed into event log.
    system_info = SystemInfo()
    self.log = {
        'args': self.args.ToDict(),
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

    # Process service arguments with the Args class, taking test-wide
    # argument values as default if service argument is absent.  Now, we only
    # need to read the self.args.services dictionary to get any _SERVICE_ARGS or
    # _SHARED_ARGS values.
    args_dict = self.args.ToDict()
    service_args = []
    for arg in self._SERVICE_ARGS + self._SHARED_ARGS:
      service_args.append(Arg(
          name=arg.name,
          type=arg.type,
          help=arg.help,
          default=args_dict.get(arg.name, arg.default),
          optional=arg.optional))
    service_arg_parser = Args(*service_args)
    if not isinstance(self.args.services, list):
      self.args.services = [self.args.services]
    new_services = []
    for service_dict in self.args.services:
      new_services.append(service_arg_parser.Parse(service_dict))
    self.args.services = new_services

    # Keyboard lights and arduino pins.
    self._StartOperatorFeedback()

    # Ensure all required services are enabled.
    for service in _SERVICE_LIST:
      if GetServiceStatus(service) == Status.STOP:
        SetServiceStatus(service, Status.START)

    # Initialize our WifiProxy library.
    self.wifi = wifi_proxy.WifiProxy()

    # Since in some test set-ups, the ethernet interface will be on the same
    # subnet as the wireless interface, we need to first disable ethernet to
    # avoid the throughput test being routed through a wired connection.
    # TODO(kitching): Change the network topology of tests with this problem so
    # that we don't have to take down ethernet.  This way, goofy-split won't
    # disconnect its display when the test is run.
    if self.args.disable_eth:
      logging.info('Disabling ethernet interfaces')
      SwitchEthernetInterfaces(False)

  def tearDown(self):
    self._EndOperatorFeedback()

    # Enable ethernet devices.
    if self.args.disable_eth:
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

  def _RunOneServiceCheck(self, ap_config):
    # Set up logging dict.
    ap_log = {
        'ifconfig': None,
        'iwconfig': None,
        'ap': None,
        'iperf_rx': None,
        'iperf_tx': None,
        'failures': []}

    # Try connecting.
    try:
      factory.console.info('Trying to connect to service %s...', ap_config.ssid)
      service = self._ConnectToService(
          ssid=ap_config.ssid,
          password=ap_config.password,
          min_signal_strength=ap_config.min_signal_strength)
    except Exception as e:
      ap_log['failures'].append(e.message)
      factory.console.info('Failed connecting to service %s', ap_config.ssid)
      logging.exception(e.message)
      return ap_log

    # Show ifconfig and iwconfig output.
    ap_log['ifconfig'] = process_utils.SpawnOutput(
        ['ifconfig'], check_call=True, log=True)
    logging.info(ap_log['ifconfig'])
    ap_log['iwconfig'] = process_utils.SpawnOutput(
        ['iwconfig'], check_call=True, log=True)
    logging.info(ap_log['iwconfig'])

    # Save network ssid details.
    ap_log['ap'] = {
        'ssid': self.wifi.get_dbus_property(service, 'Name'),
        'security': self.wifi.get_dbus_property(service, 'Security'),
        'strength': self.wifi.get_dbus_property(service, 'Strength'),
        'bssid': self.wifi.get_dbus_property(service, 'WiFi.BSSID'),
        'frequency': self.wifi.get_dbus_property(service, 'WiFi.Frequency')}

    # Try to test throughput with iperf if requested.
    if ap_config.iperf_host is not None:
      try:
        factory.console.info('Trying to run iperf on host %s...',
            ap_config.iperf_host)
        # _RunIperfAndCheckOutput returns a dict with keys:
        # ['iperf_rx', 'iperf_tx', 'failures']
        # We "update" the current AP's log to overwrite the existing empty
        # values.
        ap_log.update(self._RunIperfAndCheckOutput(
            iperf_host=ap_config.iperf_host,
            transmit_time=ap_config.transmit_time,
            transmit_interval=ap_config.transmit_interval,
            min_rx_throughput=ap_config.min_rx_throughput,
            min_tx_throughput=ap_config.min_tx_throughput))
      except Exception as e:
        ap_log['failures'].append(e.message)
      finally:
        if ap_log['failures']:
          factory.console.info('Ran iperf on host %s with errors:',
              ap_config.iperf_host)
          for failure in ap_log['failures']:
            factory.console.info(failure)
            logging.exception(failure)

    # Finally, disconnect from this network.
    if not self.wifi.disconnect_service_synchronous(
        service, _DEFAULT_TIMEOUT_SECS):
      error_str = 'Failed to disconnect from %s' % ap_config.ssid
      ap_log['failures'].append(error_str)
      logging.info(error_str)
    else:
      logging.info('Disconnected successfully from %s', ap_config.ssid)

    # Return success status.
    return ap_log

  def runTest(self):
    self._RunTestChecks()

    # Run a basic SSID list test.
    found_ssids = self._RunBasicSSIDList()
    if found_ssids:
      factory.console.info('Found services: %s', ', '.join(found_ssids))
      self.log['ssid_list'] = found_ssids
    else:
      logging.info('No services found')

    # Test WiFi signal strength for each service.
    if self.args.services:
      for ap_config in self.args.services:
        self.log['test'][ap_config.ssid] = self._RunOneServiceCheck(ap_config)

    # Log this test run.
    self._Log()

    # Check for any failures and report them.
    all_failures = []
    for ssid, ap_log in self.log['test'].iteritems():
      for error_msg in ap_log['failures']:
        all_failures.append((ssid, error_msg))
    if all_failures:
      error_msg = ('Error in connecting and/or running iperf '
                   'on one or more services')
      factory.console.info(error_msg)
      for (ssid, failure) in all_failures:
        factory.console.info("[SSID %s] %s" % (ssid, failure))
      self.fail(error_msg)
