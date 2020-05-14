# Copyright 2013 The Chromium OS Authors. All rights reserved.
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
import random
import re
import string
import uuid

import yaml

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import rf
from cros.factory.test.rf import e5071c_scpi
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import connection_manager
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import net_utils


# The root of the pytests vswr folder. The config path is relative to this when
# we load the config file locally.
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))


class VSWR(test_case.TestCase):
  """A test for antennas using Agilent E5017C Network Analyzer (ENA)."""
  ARGS = [
      Arg('event_log_name', str, 'Name of the event_log, like '
          '"vswr_prepressed" or "vswr_postpressed".'),
      Arg('config_path', str, 'Configuration path relative to the root of '
          'pytest vswr folder. E.g. path/to/config_file_name. Can use '
          '``retrieve_parameter`` pytest for downloading latest config files.',
          default=None),
      Arg('timezone', str, 'Timezone of shopfloor.', default='Asia/Taipei'),
      Arg('serial_number_key', str, 'The key referring to the serial number in '
          'question. This key will be used to retrieve the serial number from '
          'the shared data. Default key is `serial_number`.',
          default='serial_number'),
      Arg('keep_raw_logs', bool,
          'Whether to attach the log by Testlog',
          default=True)
  ]

  def setUp(self):
    self._station = device_utils.CreateStationInterface()
    self._serial_number = device_data.GetSerialNumber(
        self.args.serial_number_key)
    if self._serial_number is None:
      self.fail('Serial number does not exist.')
    self.log = {
        'config': {
            'file_path': None,
            'content': None},
        'dut': {
            'serial_number': self._serial_number},
        'network_analyzer': {
            'calibration_traces': None,
            'id': None,
            'ip': None},
        'test': {
            'start_time': datetime.datetime.now(),
            'end_time': None,
            'fixture_id': None,
            # TODO(littlecvr): These 2 will always be the same everytime,
            #                  consider removing them?
            'path': session.GetCurrentTestPath(),
            'invocation': session.GetCurrentTestInvocation(),
            'hash': str(uuid.uuid4()),  # new hash for this iteration
            'traces': {},  # wifi_main, wifi_aux, lte_main, lte_aux
            'results': {},  # wifi_main, wifi_aux, lte_main, lte_aux
            'failures': []}}

    logging.info(
        '(config_path: %s, timezone: %s)',
        self.args.config_path, self.args.timezone)

    # Set timezone.
    os.environ['TZ'] = self.args.timezone
    # The following attributes will be overridden when loading config.
    self._config = {}
    self._ena = None
    # Serial specific config attributes.
    self._sn_config = None
    # Clear results.
    self._vswr_detail_results = {}
    self._results = {}
    self.test_passed = False

    # Group checker and details for Testlog
    self._group_checker = testlog.GroupParam(
        'trace_data', ['name', 'trace_data', 'frequency'])
    testlog.UpdateParam('name', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('trace_data', value_unit='dB')
    testlog.UpdateParam('frequency', value_unit='Hz',
                        param_type=testlog.PARAM_TYPE.argument)

  def _ConnectToENA(self, network_analyzer_config):
    """Connnects to the ENA and initializes the SCPI object."""
    valid_ping_count = 0
    for ena_ip in network_analyzer_config['possible_ips']:
      # Ping the host
      logging.info('Searching for ENA at %s...', ena_ip)
      if connection_manager.PingHost(ena_ip, 2) != 0:
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
    self._ena = e5071c_scpi.ENASCPI(self.log['network_analyzer']['ip'])
    # Check if this is an expected ENA.
    self.log['network_analyzer']['id'] = self._ena.GetSerialNumber()
    logging.info('Connected to ENA %s.', self.log['network_analyzer']['id'])

  def _SerializeTraces(self, traces):
    result = {}
    for parameter in traces.parameters:
      response = {}
      for i, val in enumerate(traces.x_axis):
        response[rf.Frequency.FromHz(val).MHzi()] = traces.traces[parameter][i]
      result[parameter] = response
    return result

  def _LoadConfig(self, config_content):
    """Reads the configuration from a file."""
    logging.info('Loading config')
    self._config = yaml.load(config_content)

    self.log['config']['file_path'] = self.args.config_path
    self.log['config']['content'] = self._config
    testlog.UpdateParam('config_content',
                        param_type=testlog.PARAM_TYPE.argument)
    testlog.LogParam('config_content', self._config)

  def _LoadParametersFromLocalDisk(self):
    """Loads parameters from local disk."""
    config_path = os.path.join(LOCAL_DIR, self.args.config_path)
    with open(config_path, 'r') as f:
      self._LoadConfig(f.read())

  def _GetConfigForSerialNumber(self):
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
      The first config that matches the serial number.
    Raises:
      ValueError if the serial number is not matched.
    """
    device_models = self._config['test']['device_models']
    for sn_config in device_models:
      if re.search(sn_config['serial_number_regex'], self._serial_number):
        logging.info('SN matched config %s.', sn_config['name'])
        return sn_config
    valid_patterns = [config['serial_number_regex'] for config in device_models]
    raise ValueError('serial number %s is not matched. Valid patterns are: %s' %
                     (self._serial_number, valid_patterns))

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
      session.console.info(
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

  def _TestAntennas(self, measurement_sequence, default_thresholds):
    """Tests either main or aux antenna for both cellular and wifi."""
    def _PortName(port_number):
      return 'S%s%s' % (port_number, port_number)

    # Make sure the segment is correct.
    self._ena.SetSweepSegments([(
        self._config['network_analyzer']['measure_segment']['min_frequency'],
        self._config['network_analyzer']['measure_segment']['max_frequency'],
        self._config['network_analyzer']['measure_segment']['sample_points'])])

    # TODO(littlecvr): Name is not right.
    ports = list(measurement_sequence)
    traces = self._ena.GetTraces(list(map(_PortName, ports)))
    trace = self._SerializeTraces(traces)

    self.test_passed = True
    for port in ports:
      rf_port = _PortName(port)
      antenna_name = measurement_sequence[port]['name']
      thresholds_list = measurement_sequence[port]['thresholds']
      if not thresholds_list:
        thresholds_list = {}

      self.log['test']['traces'][antenna_name] = trace[rf_port]
      self._LogTrace(trace[rf_port], 'result_trace_%s' % antenna_name)

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
          state.TestState.PASSED if all_passed else state.TestState.FAILED)
      self.test_passed = self.test_passed and all_passed

  def _GenerateFinalResult(self):
    """Generates the final result."""
    self.log['test']['end_time'] = datetime.datetime.now()

  def _SaveLog(self):
    """Saves the logs and writes event log."""
    logging.info('Writing log with SN: %s.', self._serial_number)

    # Feed into event log.
    logging.info('Feeding into event log.')
    event_log_fields = {
        'fixture_id': self.log['test']['fixture_id'],
        'panel_serial': self._serial_number}
    event_log_fields.update(self.log)
    event_log.Log(self.args.event_log_name, **event_log_fields)

    if self.args.keep_raw_logs:
      testlog.AttachContent(
          content=yaml.dump(self.log, default_flow_style=False),
          name='vswr.yaml',
          description='plain text log of vswr')

  def _SetUpNetwork(self, host_config):
    """Sets up the local network.

    Please see the sample config file on how the network config should look
    like (it's under host -> network).
    """
    logging.info('Setting up network...')
    network_config = host_config['network']

    # Flush route cache just in case.
    self._station.CheckCall(['ip', 'route', 'flush', 'cache'])

    # Use the default interface if local_ip is not given.
    interface = network_config['interface']
    if interface == 'auto':
      pass  # do nothing
    else:
      # Replace 'default' with real interface name if necessary.
      if 'default' in interface:
        default_interface = net_utils.FindUsableEthDevice(raise_exception=True)
        logging.info('Default interface is %s.', default_interface)
        interface = str.replace(interface, 'default', default_interface)

      ip = network_config['ip']
      netmask = network_config['netmask']
      logging.info(
          'Set interface %s as %s/%s.', interface, ip, netmask)
      self._station.CheckCall(['ifconfig', interface, ip, 'netmask', netmask])
      # Make sure the underlying interface is up.
      self._station.CheckCall(['ifconfig', interface.split(':')[0], 'up'])

  def _ShowResults(self):
    """Displays the final result."""
    self.ui.SetHTML(self._serial_number, id='result-serial-number')

    # TODO(littlecvr): Don't construct HTML string directly.
    result_html_string = ''
    row_count = 1
    for measurement_sequence in self._sn_config['measurement_sequence']:
      for port in measurement_sequence:
        antenna_name = measurement_sequence[port]['name']
        if self._results[antenna_name] == state.TestState.PASSED:
          result_html_string += (
              '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                  row_count, antenna_name, self._results[antenna_name]))
        else:
          result_html_string += (
              '<tr><td>%s</td><td>%s</td><td style="color:red">%s</td></tr>' % (
                  row_count, antenna_name, self._results[antenna_name]))
        row_count += 1
    self.ui.SetHTML(result_html_string, id='result-table')

  def _ShowMessageBlock(self, html_id):
    """Helper function to display HTML message block.

    This function also hides other message blocks as well. Leaving html_id the
    only block to display.
    """
    self.ui.CallJSFunction('showMessageBlock', html_id)

  def runTest(self):
    """Runs the test.

    At each step, we first call self._ShowMessageBlock(BLOCK_ID) to display the
    message we want. (See the HTML file for all message IDs.) Then we do
    whatever we want at that step, e.g. calling
    self._LoadParametersFromLocalDisk(). Then maybe we wait for some
    specific user's action like pressing the ENTER key to continue, e.g.
    self._WaitForKey(test_ui.ENTER_KEY).
    """
    # Load config.
    self._ShowMessageBlock('load-parameters-from-local-disk')
    self._LoadParametersFromLocalDisk()

    # Check the DUT serial number is valid.
    self._sn_config = self._GetConfigForSerialNumber()

    # Connect to the network analyzer.
    self._ShowMessageBlock('set-up-network')
    self._SetUpNetwork(self._config['host'])
    self._ShowMessageBlock('connect-to-ena')
    self._ConnectToENA(self._config['network_analyzer'])

    # Check the network analyzer is calibrated.
    self._ShowMessageBlock('prepare-calibration')
    self.ui.WaitKeysOnce(test_ui.ENTER_KEY)
    self._ShowMessageBlock('check-calibration')
    ena_config = self._config['network_analyzer']
    calibration_passed, calibration_traces = self._ena.CheckCalibration(
        rf.Frequency.FromHz(ena_config['measure_segment']['min_frequency']),
        rf.Frequency.FromHz(ena_config['measure_segment']['max_frequency']),
        ena_config['measure_segment']['sample_points'],
        ena_config['calibration_check_thresholds']['min'],
        ena_config['calibration_check_thresholds']['max'])
    self.log['network_analyzer']['calibration_traces'] = calibration_traces

    for rf_port, trace in self._SerializeTraces(calibration_traces).items():
      self._LogTrace(trace, 'calibration_trace_%s' % rf_port,
                     ena_config['calibration_check_thresholds']['min'],
                     ena_config['calibration_check_thresholds']['max'])

    if not calibration_passed:
      self._ShowMessageBlock('need-calibration')
      self.ui.WaitKeysOnce(test_ui.ENTER_KEY)
      self.fail('The network analyzer needs calibration.')

    self._ShowMessageBlock('prepare-panel')
    self.ui.WaitKeysOnce(test_ui.ENTER_KEY)

    for measurement_sequence in self._sn_config['measurement_sequence']:
      # Pick a random letter to prevent the operator from pressing too fast.
      letter = random.choice(string.ascii_uppercase)
      session.console.info('Press %s to continue', letter)
      # TODO(littlecvr): Should not construct HTML string here.
      html = []
      for port in measurement_sequence:
        antenna_name = measurement_sequence[port]['name']
        html.append(
            _('Make sure the {name} antennta is connected to port {port}<br>',
              name=antenna_name,
              port=port))
      html.append(_('Then press key "{key}" to next stage.', key=letter))
      self.ui.SetHTML(html, id='state-prepare-antennas')
      self._ShowMessageBlock('prepare-antennas')
      self.ui.WaitKeysOnce(letter)

      self._ShowMessageBlock('test-antennas')
      # TODO(littlecvr): Get rid of _sn_config.
      if 'default_thresholds' in self._sn_config:
        default_thresholds = self._sn_config['default_thresholds']
      elif 'default_thresholds' in self._config['test']:
        default_thresholds = self._config['test']['default_thresholds']
      else:
        default_thresholds = (None, None)
      self._TestAntennas(measurement_sequence, default_thresholds)

    # Save log and show the result.
    self._GenerateFinalResult()
    self._ShowMessageBlock('save-log')
    self._SaveLog()
    self._ShowResults()
    self._ShowMessageBlock('show-result')
    self.ui.WaitKeysOnce(test_ui.ENTER_KEY)
    if not self.test_passed:
      self.fail()

  def _LogTrace(self, trace, name, min=None, max=None):
    """Uses testlog to log the trace data.

    Args:
      trace: the dict which key is frequency and value is the trace result.
      name: the name of the trace data.
      min: the minimum threshold of the trace.
      max: the maximum threshold of the trace.
    """
    # pylint: disable=redefined-builtin
    if min is None and max is None:
      for freq, data in trace.items():
        with self._group_checker:
          testlog.LogParam('name', name)
          testlog.LogParam('trace_data', data)
          testlog.LogParam('frequency', freq)
    else:
      for freq, data in trace.items():
        with self._group_checker:
          testlog.LogParam('name', name)
          testlog.CheckNumericParam('trace_data', data, min=min, max=max)
          testlog.LogParam('frequency', freq)
