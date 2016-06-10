# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""VSWR measures the efficiency of the transmission line.

Background:
  SWR (Standing Wave Ratio) is the ratio of the amplitude of a partial
  standing wave at an antinode (maximum) to the amplitude at an adjacent node
  (minimum). SWR is usually defined as a voltage ratio called the VSWR, but
  it is also possible to define the SWR in terms of current, resulting in the
  ISWR, which has the same numerical value. The power standing wave ratio
  (PSWR) is defined as the square of the VSWR.

Why do we need VSWR?
  A problem with transmission lines is that impedance mismatches in the cable
  tend to reflect the radio waves back to the source, preventing the power from
  reaching the destination. SWR measures the relative size of these
  reflections. An ideal transmission line would have an SWR of 1:1, with all
  the power reaching the destination and none of the power reflected back. An
  infinite SWR represents complete reflection, with all the power reflected
  back down the cable.

This test measures VSWR value using an Agilent E5071C Network Analyzer (ENA).
"""


import datetime
import logging
import os
import posixpath
import Queue
import random
import re
import shutil
import string
import StringIO
import time
import unittest
import uuid
import xmlrpclib
import yaml

import factory_common  # pylint: disable=W0611

from cros.factory.goofy.connection_manager import PingHost
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test import rf
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.rf.e5071c_scpi import ENASCPI
from cros.factory.test.utils.media_utils import MountedMedia
from cros.factory.test.utils.media_utils import RemovableDiskMonitor
from cros.factory.utils import file_utils
from cros.factory.utils import time_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.net_utils import FindUsableEthDevice
from cros.factory.utils.process_utils import Spawn


class VSWR(unittest.TestCase):
  """A test for antennas using Agilent E5017C Network Analyzer (ENA).

  In general, a pytest runs on a DUT, and runs only once. However, this test
  runs on a host Chromebook that controls the ENA, and runs forever because it
  was designed to test many antennas.

  Ideally, the test won't stop after it has been started. But practically, to
  prevent operators from overusing some accessories. It will stop after reaching
  self._config['test']['max_iterations']. This will remind the operator to
  change those accessories.
  """
  ARGS = [
      Arg('event_log_name', str, 'Name of the event_log, like '
          '"vswr_prepressed" or "vswr_postpressed".', optional=False),
      Arg('shopfloor_log_dir', str, 'Directory in which to save logs on '
          'shopfloor.  For example: "vswr_prepressed" or "vswr_postpressed".',
          optional=False),
      Arg('config_path', str, 'Configuration path relative to the root of USB '
          'disk or shopfloor parameters. E.g. path/to/config_file_name.',
          optional=True),
      Arg('timezone', str, 'Timezone of shopfloor.', default='Asia/Taipei'),
      Arg('load_from_shopfloor', bool, 'Whether to load parameters from '
          'shopfloor or not.', default=True),
  ]

  def __init__(self, *args, **kwargs):
    super(VSWR, self).__init__(*args, **kwargs)

    self._config = None
    self._usb_path = None

    self.log = {
        'config': {
            'file_path': None,
            'content': None},
        'dut': {
            'serial_number': None},
        'network_analyzer': {
            'calibration_traces': None,
            'id': None,
            'ip': None},
        'test': {
            'start_time': None,
            'end_time': None,
            'fixture_id': None,
            # TODO(littlecvr): These 2 will always be the same everytime,
            #                  consider removing them?
            'path': os.environ.get('CROS_FACTORY_TEST_PATH'),
            'invocation': os.environ.get('CROS_FACTORY_TEST_INVOCATION'),
            'hash': str(uuid.uuid4()),  # new hash for this iteration
            'traces': {},  # wifi_main, wifi_aux, lte_main, lte_aux
            'results': {},  # wifi_main, wifi_aux, lte_main, lte_aux
            'failures': []}}

  def _ConnectToENA(self, network_analyzer_config):
    """Connnects to the ENA and initializes the SCPI object."""
    valid_ping_count = 0
    for ena_ip in network_analyzer_config['possible_ips']:
      # Ping the host
      logging.info('Searching for ENA at %s...', ena_ip)
      if PingHost(ena_ip, 2) != 0:
        logging.info('Not found at %s.', ena_ip)
      else:
        logging.info('Found ENA at %s.', ena_ip)
        valid_ping_count += 1
        self.log['network_analyzer']['ip'] = ena_ip
    if valid_ping_count != 1:
      raise Exception(
          'Found %d ENAs which should be only 1.' % valid_ping_count)
    logging.info('IP of ENA automatic detected as %s',
                 self.log['network_analyzer']['ip'])

    # Set up the ENA host.
    logging.info('Connecting to ENA...')
    # TODO(littlecvr): Don't acquire ENA's IP via self.log.
    self._ena = ENASCPI(self.log['network_analyzer']['ip'])
    # Check if this is an expected ENA.
    self.log['network_analyzer']['id'] = self._ena.GetSerialNumber()
    logging.info('Connected to ENA %s.', self.log['network_analyzer']['id'])

  def _DownloadParametersFromShopfloor(self):
    """Downloads parameters from shopfloor."""
    logging.info('Downloading parameters from shopfloor...')

    shopfloor_server = shopfloor.GetShopfloorConnection(retry_interval_secs=3)
    config_content = shopfloor_server.GetParameter(self.args.config_path)

    logging.info('Parameters downloaded.')
    # Parse and load parameters.
    self._LoadConfig(config_content.data)

  def _ResetDataForNextTest(self):
    """Resets internal data for the next testing cycle."""
    logging.info('Reset internal data.')
    self.log['dut']['serial_number'] = None
    self.log['test']['start_time'] = None
    self.log['test']['end_time'] = None
    self.log['test']['hash'] = str(uuid.uuid4())  # new hash for this iteration
    self.log['test']['traces'] = {}  # wifi_main, wifi_aux, lte_main, lte_aux
    self.log['test']['results'] = {}  # wifi_main, wifi_aux, lte_main, lte_aux
    self.log['test']['failures'] = []
    self.log['test']['start_time'] = datetime.datetime.now()

  def _SerializeTraces(self, traces):
    result = {}
    for parameter in traces.parameters:
      response = {}
      for i in range(len(traces.x_axis)):
        response[rf.Frequency.FromHz(traces.x_axis[i]).MHzi()] = (
            traces.traces[parameter][i])
      result[parameter] = response
    return result

  def _LoadConfig(self, config_content):
    """Reads the configuration from a file."""
    logging.info('Loading config')
    self._config = yaml.load(config_content)

    self.log['config']['file_path'] = self.args.config_path
    self.log['config']['content'] = self._config

  def _SetUSBPath(self, usb_path):
    """Updates the USB device path."""
    self._usb_path = usb_path
    logging.info('Found USB path %s', self._usb_path)

  def _LoadParametersFromUSB(self):
    """Loads parameters from USB."""
    with MountedMedia(self._usb_path, 1) as config_root:
      config_path = os.path.join(config_root, self.args.config_path)
      with open(config_path, 'r') as f:
        self._LoadConfig(f.read())

  def _RaiseUSBRemovalException(self, unused_event):
    """Prevents unexpected USB removal."""
    raise Exception('USB removal is not allowed during test.')

  def _WaitForValidSN(self):
    """Waits for the operator to enter/scan a valid serial number.

    This function essentially does the following things:
      1. Asks the operator to enter/scan a serial number.
      2. Checks if the serial number is valid.
      3. If yes, returns.
      4. If not, shows an error message and goes to step 1.

    After the function's called. self._serial_number would contain the serial
    number entered/scaned by the operator. And self._sn_config would contain
    the config corresponding to that serial number. See description of the
    _GetConfigForSerialNumber() function for more info about 'corresponding
    config.'
    """
    def _GetConfigForSerialNumber(serial_number):
      """Searches the suitable config for this serial number.

      TODO(littlecvr): Move the following description to the module level
                       comment block, where it should state the structure of
                       config file briefly.

      In order to utilize a single VSWR fixture as multiple stations, the
      config file was designed to hold different configs at the same time.
      Thus, this function searches through all the configs and returns the
      first config that matches the serial number, or None if no match.

      For example: the fixture can be configured such that if the serial number
      is between 001 to 100, the threshold is -30 to 0.5; if the serial number
      is between 101 to 200, the threshold is -40 to 0.5; and so forth.

      Returns:
        The first config that matches the serial number, or None if no match.
      """
      for sn_config in self._config['test']['device_models']:
        if re.search(sn_config['serial_number_regex'], serial_number):
          logging.info('SN matched config %s.', sn_config['name'])
          return sn_config
      return None

    # Reset SN input box and hide error message.
    self._ui.RunJS('resetSNField()')
    self._ShowMessageBlock('enter-sn')
    # Loop until the right serial number has been entered.
    while True:
      # Focus and select the text for convenience.
      self._ui.RunJS('$("sn").select()')
      self._WaitForKey(test_ui.ENTER_KEY)
      serial_number = self._GetSN()
      self._sn_config = _GetConfigForSerialNumber(serial_number)
      if self._sn_config:
        self.log['dut']['serial_number'] = serial_number
        return
      else:
        self._ui.RunJS('$("sn-format-error-value").innerHTML = "%s"' %
                       serial_number)
        self._ui.RunJS('$("sn-format-error").style.display = ""')

  def _CaptureScreenshot(self, filename_prefix):
    """Captures the screenshot based on the settings.

    Screenshot will be saved in 3 places: ENA, USB disk, and shopfloor (if
    shopfloor is enabled). Timestamp will be automatically added as postfix to
    the output name.

    Args:
      filename_prefix: prefix for the image file name.
    """
    # Save a screenshot copy in ENA.
    filename = '%s[%s]' % (filename_prefix, time_utils.TimeString(
        time_separator='-', milliseconds=False))
    png_content = self._ena.CaptureScreenshot()
    event_log.Log('vswr_screenshot',
                  ab_serial_number=self._serial_number,
                  path=self._config['event_log_name'],
                  filename=filename)

    with file_utils.UnopenedTemporaryFile() as temp_png_path:
      with open(temp_png_path, 'w') as f:
        f.write(png_content)

      # Save screenshot to USB disk.
      formatted_date = time.strftime('%Y%m%d', time.localtime())
      logging.info('Saving screenshot to USB under dates %s', formatted_date)
      with MountedMedia(self._usb_path, 1) as mount_dir:
        target_dir = os.path.join(mount_dir, formatted_date, 'screenshot')
        file_utils.TryMakeDirs(target_dir)
        filename_in_abspath = os.path.join(target_dir, filename)
        shutil.copyfile(temp_png_path, filename_in_abspath)
        logging.info('Screenshot %s saved in USB.', filename)

      # Save screenshot to shopfloor if needed.
      if self._config['shopfloor_enabled']:
        logging.info('Sending screenshot to shopfloor')
        log_name = os.path.join(self._config['shopfloor_log_dir'],
                                'screenshot', filename)
        self._UploadToShopfloor(
            temp_png_path, log_name,
            ignore_on_fail=self._config['shopfloor_ignore_on_fail'],
            timeout=self._config['shopfloor_timeout'])
        logging.info('Screenshot %s uploaded.', filename)

  def _CheckMeasurement(self, threshold, extracted_value,
                        print_on_failure=False, freq=None, title=None):
    """Checks if the measurement meets the spec.

    Failure details are also recorded in the eventlog. Console display is
    controlled by print_on_failure.

    Args:
      threshold: the pre-defined (min, max) signal strength threshold.
      extracted_value: the value acquired from the trace.
      print_on_failure: If True, outputs failure band in Goofy console.
      freq: frequency to display when print_on_failure is enabled.
      title: title to display for failure message (when print_on_failure is
          True), usually it's one of 'cell_main', 'cell_aux', 'wifi_main',
          'wifi_aux'.
    """
    min_value = threshold['min']
    max_value = threshold['max']
    difference = max(
        (min_value - extracted_value) if min_value else 0,
        (extracted_value - max_value) if max_value else 0)
    check_pass = (difference <= 0)

    if (not check_pass) and print_on_failure:
      # Highlight the failed freqs in console.
      factory.console.info(
          '%10s failed at %.0f MHz[%9.3f dB], %9.3f dB '
          'away from threshold[%s, %s]',
          title, freq.MHzi(), float(extracted_value),
          float(difference), min_value, max_value)
    # Record the detail for event_log.
    self._vswr_detail_results['%dM' % freq.MHzi()] = {
        'type': title,
        'freq': freq.Hzf(),
        'observed': extracted_value,
        'result': check_pass,
        'threshold': [min_value, max_value],
        'diff': difference}
    return check_pass

  def _UploadToShopfloor(
      self, file_path, log_name, ignore_on_fail=False, timeout=10):
    """Uploads a file to shopfloor server.

    Args:
      file_path: local file to upload.
      log_name: file_name that will be saved under shopfloor.
      ignore_on_fail: if exception will be raised when upload fails.
      timeout: maximal time allowed for getting shopfloor instance.
    """
    try:
      with open(file_path, 'r') as f:
        chunk = f.read()
      description = 'aux_logs (%s, %d bytes)' % (log_name, len(chunk))
      start_time = time.time()
      shopfloor_client = shopfloor.get_instance(detect=True, timeout=timeout)
      shopfloor_client.SaveAuxLog(log_name, xmlrpclib.Binary(chunk))
      logging.info(
          'Successfully uploaded %s in %.03f s',
          description, time.time() - start_time)
    except Exception as e:
      if ignore_on_fail:
        factory.console.info(
            'Failed to sync with shopfloor for [%s], ignored', log_name)
        return False
      else:
        raise e
    return True

  def _TestAntennas(self, measurement_sequence, default_thresholds):
    """Tests either main or aux antenna for both cellular and wifi."""
    # Make sure the segment is correct.
    self._ena.SetSweepSegments([(
        self._config['network_analyzer']['measure_segment']['min_frequency'],
        self._config['network_analyzer']['measure_segment']['max_frequency'],
        self._config['network_analyzer']['measure_segment']['sample_points'])])

    # TODO(littlecvr): Name is not right.
    ports = measurement_sequence.keys()
    rf_ports = []
    for port in ports:
      rf_ports.append('S%s%s' % (port, port))
    traces = self._ena.GetTraces(rf_ports)
    for port in ports:
      rf_port = 'S%s%s' % (port, port)
      antenna_name = measurement_sequence[port]['name']
      thresholds_list = measurement_sequence[port]['thresholds']
      if not thresholds_list:
        thresholds_list = {}

      trace = self._SerializeTraces(traces)
      self.log['test']['traces'][antenna_name] = trace[rf_port]

      # Check all sample points.
      results = {}
      all_passed = True
      # TODO(littlecvr): Should skip particular frequencies specified by user,
      #                  although specified frequencies are normally tighter.
      # Check default thresholds.
      for frequency in traces.x_axis:
        frequency = rf.Frequency.FromHz(frequency)
        response = traces.GetFreqResponse(frequency.Hzf(), rf_port)
        passed = self._CheckMeasurement(
            default_thresholds, response, print_on_failure=True,
            freq=frequency, title=antenna_name)
        all_passed = all_passed and passed
      # Check specified frequencies.
      for frequency, thresholds in thresholds_list.items():
        frequency = rf.Frequency.FromMHz(frequency)
        response = traces.GetFreqResponse(frequency.Hzf(), rf_port)
        passed = self._CheckMeasurement(
            thresholds, response, print_on_failure=True,
            freq=frequency, title=antenna_name)
        results[frequency.MHzi()] = {
            'value': response,
            'thresholds': thresholds,
            'passed': passed}
        all_passed = all_passed and passed

      self.log['test']['results'][antenna_name] = results

      self._results[antenna_name] = (
          TestState.PASSED if all_passed else TestState.FAILED)

  def _GenerateFinalResult(self):
    """Generates the final result."""
    self.log['test']['end_time'] = datetime.datetime.now()

  def _SaveLog(self):
    """Saves the logs and writes event log."""
    logging.info('Writing log with SN: %s.', self.log['dut']['serial_number'])

    log_file_name = 'log_%s_%s.yaml' % (
        datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3],  # time
        self.log['dut']['serial_number'])  # serial number
    log_content = yaml.dump(self.log, default_flow_style=False)

    # Write log file to USB.
    with MountedMedia(self._usb_path, 1) as mount_dir:
      target_dir = os.path.join(
          mount_dir, self.args.shopfloor_log_dir)
      file_utils.TryMakeDirs(target_dir)
      full_path = os.path.join(target_dir, log_file_name)
      with open(full_path, 'w') as f:
        f.write(log_content)

    # Feed into event log.
    logging.info('Feeding into event log.')
    event_log_fields = {
        'fixture_id': self.log['test']['fixture_id'],
        'panel_serial': self.log['dut']['serial_number']}
    event_log_fields.update(self.log)
    event_log.Log(self.args.event_log_name, **event_log_fields)

    logging.info('Uploading aux log onto shopfloor.')
    shopfloor_server = shopfloor.GetShopfloorConnection()
    shopfloor_server.SaveAuxLog(
        posixpath.join(self.args.shopfloor_log_dir,
                       log_file_name),
        xmlrpclib.Binary(log_content))

  def _SetUpNetwork(self, host_config):
    """Sets up the local network.

    Please see the sample config file on how the network config should look
    like (it's under host -> network).
    """
    logging.info('Setting up network...')
    network_config = host_config['network']

    # Flush route cache just in case.
    Spawn(['ip', 'route', 'flush', 'cache'], check_call=True)

    # Use the default interface if local_ip is not given.
    interface = network_config['interface']
    if interface == 'auto':
      pass  # do nothing
    else:
      # Replace 'default' with real interface name if necessary.
      if 'default' in interface:
        default_interface = FindUsableEthDevice(raise_exception=True)
        logging.info('Default interface is %s.', default_interface)
        interface = str.replace(interface, 'default', default_interface)

      ip = network_config['ip']
      netmask = network_config['netmask']
      logging.info(
          'Set interface %s as %s/%s.', interface, ip, netmask)
      Spawn(['ifconfig', interface, ip, 'netmask', netmask], check_call=True)
      # Make sure the underlying interface is up.
      Spawn(['ifconfig', interface.split(':')[0], 'up'], check_call=True)

  def _ShowResults(self):
    """Displays the final result."""
    self._ui.SetHTML(self._serial_number, id='result-serial-number')

    # TODO(littlecvr): Don't construct HTML string directly.
    result_html_string = ''
    row_count = 1
    for measurement_sequence in self._sn_config['measurement_sequence']:
      for port in measurement_sequence:
        antenna_name = measurement_sequence[port]['name']
        if self._results[antenna_name] == TestState.PASSED:
          result_html_string += (
              '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                  row_count, antenna_name, self._results[antenna_name]))
        else:
          result_html_string += (
              '<tr><td>%s</td><td>%s</td><td style="color:red">%s</td></tr>' % (
                  row_count, antenna_name, self._results[antenna_name]))
        row_count += 1
    self._ui.SetHTML(result_html_string, id='result-table')

  def _WaitForEvent(self, subtype):
    """Waits until a specific event subtype has been sent."""
    while True:
      event = self._event_queue.get()
      if hasattr(event, 'subtype') and event.subtype == subtype:
        return event

  def _WaitForKey(self, key):
    """Waits until a specific key has been pressed."""
    # Create a unique event_name for the key and bind it.
    event_name = uuid.uuid4()
    self._ui.BindKey(key, lambda _: self._event_queue.put(
        Event(Event.Type.TEST_UI_EVENT, subtype=event_name)))
    self._WaitForEvent(event_name)
    # Unbind the key and delete the event_name's handler.
    self._ui.UnbindKey(key)

  def _GetSN(self):
    """Gets serial number from HTML input box."""
    self._ui.RunJS('emitSNEnterEvent()')
    event = self._WaitForEvent('snenter')
    return event.data

  def _ShowMessageBlock(self, html_id):
    """Helper function to display HTML message block.

    This function also hides other message blocks as well. Leaving html_id the
    only block to display.
    """
    self._ui.RunJS('showMessageBlock("%s")' % html_id)

  def setUp(self):
    logging.info(
        '(config_path: %s, timezone: %s, load_from_shopfloor: %s)',
        self.args.config_path, self.args.timezone,
        self.args.load_from_shopfloor)

    # Set timezone.
    os.environ['TZ'] = self.args.timezone
    # The following attributes will be overridden when loading config or USB's
    # been inserted.
    self._config = {}
    self._usb_path = ''
    self._serial_number = ''
    self._ena = None
    self._ena_name = None
    # Serial specific config attributes.
    self._sn_config = None
    self._sn_config_name = None
    self._take_screenshot = False
    self._reference_info = False
    self._marker_info = None
    self._sweep_restore = None
    self._vswr_threshold = {}
    # Clear results.
    self._raw_traces = {}
    self._log_to_file = StringIO.StringIO()
    self._vswr_detail_results = {}
    self._iteration_hash = str(uuid.uuid4())
    self._results = {}
    # Misc.
    self._current_iteration = 0

    # Set up UI.
    self._event_queue = Queue.Queue()
    self._ui = test_ui.UI()
    self._ui.AddEventHandler('keypress', self._event_queue.put)
    self._ui.AddEventHandler('snenter', self._event_queue.put)
    self._ui.AddEventHandler('usbinsert', self._event_queue.put)
    self._ui.AddEventHandler('usbremove', self._event_queue.put)

    # Set up USB monitor.
    self._monitor = RemovableDiskMonitor()
    self._monitor.Start(
        on_insert=lambda usb_path: self._ui.PostEvent(Event(
            Event.Type.TEST_UI_EVENT, subtype='usbinsert', usb_path=usb_path)),
        on_remove=lambda usb_path: self._ui.PostEvent(Event(
            Event.Type.TEST_UI_EVENT, subtype='usbremove', usb_path=usb_path)))

  def runTest(self):
    """Runs the test forever or until max_iterations reached.

    At each step, we first call self._ShowMessageBlock(BLOCK_ID) to display the
    message we want. (See the HTML file for all message IDs.) Then we do
    whatever we want at that step, e.g. calling
    self._DownloadParametersFromShopfloor(). Then maybe we wait for some
    specific user's action like pressing the ENTER key to continue, e.g.
    self._WaitForKey(test_ui.ENTER_KEY).
    """
    self._ui.Run(blocking=False)

    # Wait for USB.
    if self.args.load_from_shopfloor:
      self._ShowMessageBlock('wait-for-usb-to-save-log')
    else:
      self._ShowMessageBlock('wait-for-usb-to-load-parameters-and-save-log')
    usb_insert_event = self._WaitForEvent('usbinsert')
    self._SetUSBPath(usb_insert_event.usb_path)
    # Prevent USB from being removed from now on.
    self._ui.AddEventHandler('usbremove', self._RaiseUSBRemovalException)

    # Load config.
    if self.args.load_from_shopfloor:
      self._ShowMessageBlock('download-parameters-from-shopfloor')
      self._DownloadParametersFromShopfloor()
    else:
      self._ShowMessageBlock('load-parameters-from-usb')
      self._LoadParametersFromUSB()

    self._ShowMessageBlock('set-up-network')
    self._SetUpNetwork(self._config['host'])

    self._ShowMessageBlock('connect-to-ena')
    self._ConnectToENA(self._config['network_analyzer'])

    while True:
      self._ShowMessageBlock('check-calibration')

      ena_config = self._config['network_analyzer']
      calibration_passed, calibration_traces = self._ena.CheckCalibration(
          rf.Frequency.FromHz(ena_config['measure_segment']['min_frequency']),
          rf.Frequency.FromHz(ena_config['measure_segment']['max_frequency']),
          ena_config['measure_segment']['sample_points'],
          ena_config['calibration_check_thresholds']['min'],
          ena_config['calibration_check_thresholds']['max'])
      self.log['network_analyzer']['calibration_traces'] = calibration_traces

      if not calibration_passed:
        self._ShowMessageBlock('need-calibration')
        while True:
          time.sleep(0.5)

      self._ShowMessageBlock('prepare-panel')
      self._ResetDataForNextTest()
      self._WaitForKey(test_ui.ENTER_KEY)

      self._WaitForValidSN()

      for measurement_sequence in self._sn_config['measurement_sequence']:
        # Pick a random letter to prevent the operator from pressing too fast.
        letter = random.choice(string.ascii_uppercase)
        factory.console.info('Press %s to continue', letter)
        # TODO(littlecvr): Should not construct HTML string here.
        html_string_en = ''
        html_string_ch = ''
        for port in measurement_sequence:
          antenna_name = measurement_sequence[port]['name']
          html_string_en += (
              'Make sure the %s antennta is connected to port %s<br>' % (
                  antenna_name, port))
          html_string_ch += u'连接 %s 天线至 port %s<br>' % (antenna_name, port)
        html_string_en += 'Then press key "%s" to next stage.' % letter
        html_string_ch += u'完成后按 %s 键' % letter
        html_string = test_ui.MakeLabel(html_string_en, html_string_ch)
        self._ui.SetHTML(html_string, id='state-prepare-antennas')
        self._ShowMessageBlock('prepare-antennas')
        self._WaitForKey(letter)

        self._ShowMessageBlock('test-antennas')
        # TODO(littlecvr): Get rid of _sn_config.
        if 'default_thresholds' in self._sn_config:
          default_thresholds = self._sn_config['default_thresholds']
        elif 'default_thresholds' in self._config['test']:
          default_thresholds = self._config['test']['default_thresholds']
        else:
          default_thresholds = (None, None)
        self._TestAntennas(measurement_sequence, default_thresholds)

      self._GenerateFinalResult()

      self._ShowMessageBlock('save-log')
      self._SaveLog()

      self._ShowResults()
      self._ShowMessageBlock('show-result')
      self._WaitForKey(test_ui.ENTER_KEY)
