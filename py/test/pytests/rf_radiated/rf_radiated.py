# -*- coding: utf-8 -*-
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests WiFi/LTE chip's transmitting (TX) capability.

This tests the WiFi/LTE chip's TX capability with different antenna combinations
(main, aux, or both), channels (frequencies), bandwidths, data rates, power,
etc.  To achieve this, we need to tell the chip to enter a special mode called
"MFG" (manufacturing) mode, which enables finer control of the chip.  Take the
WiFi chip for example: in this mode, we can tell the chip to "emit 15dBm power
on channel 1 (2142MHz), with 20MHz bandwidth, 56Mbps data rate."  After that, we
can use a power meter to measure the actual power emitted by the chip, and check
if it meets the thresholds.

This test requires a config file in YAML format.  See
"wifi_radiated_config.sample.yaml" and "lte_radiated_config.sample.yaml" for
more info.

Usage example::

  FactoryTest(
      id='WiFiRadiated',
      exclusive=['NETWORKING'],
      label_en='WiFi Radiated',
      label_zh=u'WiFi 发送测试',
      pytest_name='wifi_radiated',
      dargs={
          'config_file_path': 'rf/wifi_radiated/wifi_radiated_config.yaml',
          'enable_shopfloor': True,
          'network_settings': {'ip': '192.168.137.101',
                               'netmask': '255.255.255.0',
                               'gateway': '192.168.137.1'},
          'event_log_name': 'wifi_radiated',
          'shopfloor_log_dir': 'wifi_radiated'})

  FactoryTest(
      id='LTERadiated',
      exclusive=['NETWORKING'],
      label_en='LTE Radiated',
      label_zh=u'LTE 发送测试',
      run_if='device_data.component.has_lte',
      pytest_name='lte_radiated',
      dargs={
          'config_file_path': 'rf/lte_radiated/lte_radiated_config.yaml',
          'enable_shopfloor': False,
          'network_settings': {'ip': '192.168.137.101',
                               'netmask': '255.255.255.0',
                               'gateway': '192.168.137.1'},
          'event_log_name': 'lte_radiated'})
"""

import datetime
import logging
import os
import posixpath
import sys
import time
import traceback
import unittest
import xmlrpclib
import yaml

import factory_common  # pylint: disable=W0611

from cros.factory import system
from cros.factory.rf import n1914a
from cros.factory.test.args import Arg
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test import leds
from cros.factory.test import shopfloor
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils


class RFRadiatedTest(unittest.TestCase):

  ARGS = [
      Arg('config_file_path', str,
          'Path to config file.  If "enable_shopfloor" is True, this is '
          'interpreted as the path relative to shopfloor\'s parameter folder. '
          'If "enable_shopfloor" is False, this is interprested as a local '
          'path.  Note that in the later case, if the path starts with a '
          'slash, it is interpreted as an absolute path; otherwise, it is '
          'interpreted as a relative path (based on factory.FACTORY_PATH).',
          optional=False),
      Arg('enable_shopfloor', bool,
          'Whether to use shopfloor or not.  If True, the test will try to '
          'load config file from and upload aux log to shopfloor server.  If '
          'False, the test will try to load config file from local disk and '
          'won\'t upload aux log. ',
          optional=False),
      Arg('network_config', dict, 'A dict containing keys {interface, ip, '
          'netmask, gateway} to set on the ethernet adapter.', optional=False),
      Arg('event_log_name', str, 'Name of the event_log, like '
          '"wifi_radiated".', optional=False),
      Arg('shopfloor_log_dir', str, 'Directory in which to save logs on '
          'shopfloor.  For example: "wifi_radiated".  Only takes effect if '
          '"enable_shopfloor" is set to True.', default=None, optional=True),
      Arg('blink_keyboard_lights', bool,
          'Blink keyboard lights while running test.  Useful if test is '
          'running on a DUT within a chamber.', default=False, optional=True),
      Arg('single_profile_max_try_count', int,
          'Maximum number of tries for a single profile',
          default=1, optional=True)]

  def __init__(self, *args, **kwargs):
    super(RFRadiatedTest, self).__init__(*args, **kwargs)

    self.leds_blinker = None
    self.power_meter = None
    self.chip_controller = None

    # Initialize the log dict, which will later be fed into event log and
    # stored as an aux_log on shopfloor.
    board = system.GetBoard()
    self.log = {
        'config': {
            'file_path': None,
            'content': None},
        'dut': {
            'antenna_model': None,
            'device_id': event_log.GetDeviceId(),
            'mac_address': net_utils.GetWLANMACAddress(),
            'serial_number': board.GetSerialNumber(),
            'mlb_serial_number': board.GetMlbSerialNumber(),
            'nvidia_serial_number': board.GetNvidiaSerialNumber()},
        'test': {
            'start_time': None,
            'end_time': None,
            'fixture_id': None,
            'path': os.environ.get('CROS_FACTORY_TEST_PATH'),
            'invocation': os.environ.get('CROS_FACTORY_TEST_INVOCATION'),
            'results': {},  # A dict of test profile name to measured power.
            'failures': []},  # A list exceptions and tracebacks.
        'power_meter': {
            'mac_address': None}}

  def setUp(self):
    # We're in the chamber without a monitor.  Start blinking keyboard LEDs to
    # inform the operator that we're still working.
    if self.args.blink_keyboard_lights:
      self.leds_blinker = leds.Blinker(
          [(0, 0.5), (leds.LED_NUM | leds.LED_CAP | leds.LED_SCR, 0.5)])
      self.leds_blinker.Start()

    # TODO(littlecvr): Enable fine controls in engineering mode.

    # All the following steps are critical, should die if anything goes wrong.
    try:
      # Set up network manually because we're in network exclusive mode.
      self._SetUpNetwork(self.args.network_config)

      # Load config file either from shopfloor or local disk.
      if self.args.enable_shopfloor:
        logging.info('Loading config file from shopfloor %s.',
                     self.args.config_file_path)
        shopfloor_server = shopfloor.GetShopfloorConnection(
            retry_interval_secs=3)
        config_content = shopfloor_server.GetParameter(
            self.args.config_file_path).data
      else:
        if os.path.isabs(self.args.config_file_path):
          config_file_path = self.args.config_file_path
        else:
          config_file_path = os.path.join(
              factory.FACTORY_PATH, self.args.config_file_path)
        logging.info(
            'Loading config file from local disk %s.', config_file_path)
        with open(config_file_path, 'r') as f:
          config_content = f.read()
      self.config = yaml.load(config_content)
      # Record config content and path into the log.
      self.log['config']['content'] = self.config
      self.log['config']['file_path'] = self.args.config_file_path

      # Enter manufacturing mode.
      factory.console.info('Entering manufacturing mode.')
      self.chip_controller = self._CreateChipController(
          self.dut, self.config['chip_controller_config'])
      self.chip_controller.EnterMFGMode()

      # Set up power meter.
      logging.info('Setting up power meter.')
      self.power_meter = self._SetUpPowerMeter(
          self.config['power_meter_config'])
      # Record power meter's MAC address and fixture's ID into the log.
      power_meter_mac_address = self.power_meter.GetMACAddress()
      self.log['power_meter']['mac_address'] = power_meter_mac_address
      self.log['test']['fixture_id'] = (
          self.config['power_meter_to_fixture_id_map'].get(
              power_meter_mac_address, 'UNKNOWN_RF_FIXTURE'))
    except Exception:
      self.log['test']['failures'].append(
          ''.join(traceback.format_exception(*sys.exc_info())))
      self._EndTest()
    finally:
      raise

  def _SetUpNetwork(self, network_config):
    """Manually sets ethernet IP address and adds route to shopfloor."""
    # Find ethernet adapter and set IP.
    if 'interface' in network_config:
      interface = network_config['interface']
    else:
      interface = net_utils.FindUsableEthDevice(raise_exception=True)
    process_utils.Spawn([
        'ifconfig', interface, network_config['ip'],
        'netmask', network_config['netmask']], check_call=True)
    # Manually add route to shopfloor.
    process_utils.Spawn([
        'route', 'add', 'default', 'gw',
        network_config['gateway']], call=True)

  def _SetUpPowerMeter(self, power_meter_config):
    """Initializes the power meter, and returns the power meter object."""
    power_meter = n1914a.N1914A(power_meter_config['ip'])
    power_meter.SetRealFormat()
    for port in power_meter_config['rf_ports']:
      power_meter.SetAverageFilter(port, avg_length=None)
      power_meter.SetMode(port, power_meter_config['measurement_mode'])
      power_meter.SetTriggerToFreeRun(port)
      power_meter.SetContinuousTrigger(port)
    return power_meter

  def _CreateChipController(self, dut, chip_controller_config):
    """Creates WiFi/LTE chip controller for the current system.

    This is a virtual function that derived classes should override.

    Args:
      chip_controller_config: The 'chip_controller_config' section from the
          config file because some chip controllers require additional info to
          be set up.
    """
    raise NotImplementedError

  def runTest(self):
    # First, find antenna model.  Use 'generic' and give it a warning if no
    # antenna model specified.  This will be used later to query thresholds
    # table because different antenna models may have different thresholds.
    antenna_model = shopfloor.GetDeviceData().get('component.antenna')
    if antenna_model is None or len(antenna_model) == 0:
      antenna_model = 'generic'
      factory.console.warning(
          'No antenna model specified, will use generic thresholds.')
    else:
      logging.info('Antenna model is %r.', antenna_model)
    # Record antenna model.
    self.log['dut']['antenna_model'] = antenna_model

    # Run through all test profiles, recording the total time spent.
    self.log['test']['start_time'] = datetime.datetime.now()
    for profile in self.config['test_profiles']['antenna_%s' % antenna_model]:
      # Testing profiles are not like steps in setUp().  They're not critical,
      # so continue on errors (but still record them).
      passed = False
      failures = []
      for try_time in xrange(self.args.single_profile_max_try_count):
        factory.console.info(
            'Testing profile: %r, try %d/%d', profile['name'],
            1 + try_time, self.args.single_profile_max_try_count)
        try:
          self._TestOneSingleProfile(profile)
          passed = True
          break
        except Exception:
          failures.append(''.join(traceback.format_exception(*sys.exc_info())))
      if not passed:
        self.log['test']['failures'] += failures
    self.log['test']['end_time'] = datetime.datetime.now()

  def _TestOneSingleProfile(self, test_profile):
    """Tests a single profile.

    The function will:
      1. Set profile specific settings on power meter.
      2. Tell the chip to emit power.
      3. Measure power multiple times, and average them.
      4. Raise exception if result is not within thresholds.
    """
    # Range and frequency need to be set for every test item.
    self.power_meter.SetRange(test_profile['power_meter_rf_port'],
                              test_profile['power_meter_range'])
    self.power_meter.SetMeasureFrequency(test_profile['power_meter_rf_port'],
                                         test_profile['power_meter_frequency'])

    # Start transmitting power.
    self.chip_controller.SetParameters(test_profile)
    self.chip_controller.StartTransmitting()
    # The chip may not respond to the command immediately, so delay before
    # measuring if necessary.
    if self.config['power_meter_config']['msecs_delay_before_measuring'] > 0:
      time.sleep(self.config[
          'power_meter_config']['msecs_delay_before_measuring'] / 1000.0)
    # Measure the power for avg_length times and average them.
    power = self.power_meter.MeasureInBinary(
        test_profile['power_meter_rf_port'],
        avg_length=self.config['power_meter_config']['averaging_count'])
    # Record the result.
    factory.console.info('Got power %f.', power)
    self.log['test']['results'][test_profile['name']] = power
    # Stop transmitting power.
    self.chip_controller.StopTransmitting()

    # Check if power meets the thresholds.
    threshold_min, threshold_max = test_profile['test_power_thresholds']
    if ((threshold_min is not None and power < threshold_min) or
        (threshold_max is not None and power > threshold_max)):
      raise Exception(
          'When testing profile %r, power %f not in range [%s, %s]' % (
              test_profile['name'], power, threshold_min, threshold_max))

  def tearDown(self):
    self._EndTest()

  def _EndTest(self):
    """Tasks to do before test ends.

    The function will:
      1. Leave MFG mode and close connection to the power meter.
      2. Save into event log, and upload aux log onto shopfloor.
      3. Stop blinking USB keyboard LEDs.
      4. Raise an exception if there are any failures.

    _EndTest should never raise an exception due to internal failure.  It should
    catch internal failures and store them into self.log['test']['failures'].
    At the end of _EndTest, if there are any failures in self.log, it will raise
    an Exception with these failures.

    Raises:
      Exception if there are any failures in self.log['test']['failures'].  The
      exception message will be all failure strings joined together.
    """
    try:
      # Leave manufacturing mode.
      if self.chip_controller:
        self.chip_controller.LeaveMFGMode()
    except Exception:
      self.log['test']['failures'].append(
          'Error leaving manufacturing mode: '
          ''.join(traceback.format_exception(*sys.exc_info())))

    try:
      # Close the connection to power meter.
      if self.power_meter:
        self.power_meter.Close()
    except Exception:
      self.log['test']['failures'].append(
          'Error closing connection to power meter: '
          ''.join(traceback.format_exception(*sys.exc_info())))

    try:
      # Save into event log.
      logging.info('Saving into event log.')
      event_log_fields = {
          'fixture_id': self.log['test']['fixture_id'],
          'panel_serial': self.log['dut']['serial_number']}
      event_log_fields.update(self.log)
      event_log.Log(self.args.event_log_name, **event_log_fields)
      # Upload aux log onto shopfloor if needed.
      if self.args.enable_shopfloor and self.args.shopfloor_log_dir is not None:
        logging.info('Uploading aux log onto shopfloor.')
        log_file_name = 'log_%s_%s_%s.yaml' % (
            # time
            datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3],
            # serial number
            self.log['dut']['serial_number'],
            # MAC w/o delimeters
            self.log['dut']['mac_address'].replace(':', ''))
        log_content = yaml.dump(self.log, default_flow_style=False)
        shopfloor_server = shopfloor.GetShopfloorConnection()
        shopfloor_server.SaveAuxLog(
            posixpath.join(self.args.shopfloor_log_dir, log_file_name),
            xmlrpclib.Binary(log_content))
    except Exception:
      self.log['test']['failures'].append(
          'Error saving event log: '
          ''.join(traceback.format_exception(*sys.exc_info())))

    try:
      # Stop blinking LEDs.
      if self.leds_blinker:
        self.leds_blinker.Stop()
    except Exception:
      self.log['test']['failures'].append(
          'Error stopping LED blinking: '
          ''.join(traceback.format_exception(*sys.exc_info())))

    # Raise exception if there are any failures.
    if self.log['test']['failures']:
      raise Exception(''.join(map(str, self.log['test']['failures'])))
