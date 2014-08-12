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


import logging
import os
import pprint
import Queue
import re
import shutil
import StringIO
import time
import unittest
import urllib
import uuid
import xmlrpclib
import yaml

import factory_common  # pylint: disable=W0611

from cros.factory.event_log import Log
from cros.factory.goofy.connection_manager import PingHost
from cros.factory.goofy.goofy import CACHES_DIR
from cros.factory.rf.e5071c_scpi import ENASCPI
from cros.factory.rf.utils import CheckPower, DownloadParameters
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.test.media_util import MediaMonitor, MountedMedia
from cros.factory.test.utils import TimeString, TryMakeDirs
from cros.factory.utils import file_utils
from cros.factory.utils.net_utils import FindUsableEthDevice
from cros.factory.utils.process_utils import Spawn


class VSWR(unittest.TestCase):
  """A test for antennas using Agilent E5017C Network Analyzer (ENA).

  In general, a pytest runs on a DUT, and runs only once. However, this test
  runs on a host Chromebook that controls the ENA, and runs forever because it
  was designed to test many antennas.

  Ideally, the test won't stop after it has been started. But practically, to
  prevent operators from overusing some accessories. It will stop after
  reaching self._max_iterations. Reminding the operator to change those
  accessories.
  """

  # Items in the final result table.
  _RESULT_IDS = [
      'cell-main', 'cell-aux', 'wifi-main', 'wifi-aux', 'final-result']
  _RESULTS_TO_CHECK = [
      'cell-main', 'cell-aux', 'wifi-main', 'wifi-aux']

  ARGS = [
      Arg('config_path', str, 'Configuration path relative to the root of USB '
          'disk or shopfloor parameters. E.g. path/to/config_file_name.',
          optional=True),
      Arg('timezone', str, 'Timezone of shopfloor.', default='Asia/Taipei'),
      Arg('load_from_shopfloor', bool, 'Whether to load parameters from '
          'shopfloor or not.', default=True),
  ]

  def _CheckCalibration(self):
    """Checks if the trace are as flat as expected.

    The expected flatness is defined in calibration_check config, which is a
    tuple of:

        ((begin_freqency, end_frequency, sample_points), (min_value, max_value))

    For example:

      ((800*1E6, 6000*1E6, 100), (-0.3, 0.3))

    from 800MHz to 6GHz, sampling 100 points and requires the value to stay
    with in (-0.3, 0.3).
    """
    calibration_check = self._config.get('calibration_check', None)
    if not calibration_check:
      raise Exception('No calibration data in config file.')
    start_freq, stop_freq, sample_points = calibration_check[0]
    threshold = calibration_check[1]
    logging.info(
        'Checking calibration status from %.2f to %.2f '
        'with threshold (%f, %f)...', start_freq, stop_freq,
        threshold[0], threshold[1])
    self._ena.SetSweepSegments([(start_freq, stop_freq, sample_points)])
    TRACES_TO_CHECK = ['S11', 'S22']
    traces = self._ena.GetTraces(TRACES_TO_CHECK)
    calibration_check_passed = True
    for trace_name in TRACES_TO_CHECK:
      trace_data = traces.traces[trace_name]
      for index, freq in enumerate(traces.x_axis):
        check_point = '%s-%15.2f' % (trace_name, freq)
        power_check_passed = CheckPower(
            check_point, trace_data[index], threshold)
        if not power_check_passed:
          # Do not stop, continue to find all failing parts.
          factory.console.info(
              'Calibration check failed at %s', check_point)
          calibration_check_passed = False
    if calibration_check_passed:
      logging.info('Calibration check passed.')
    else:
      raise Exception('Calibration check failed.')

  def _ConnectToENA(self):
    """Connnects to E5071C (ENA) and initializes the SCPI object."""
    # Set up the ENA host.
    logging.info('Connecting to ENA...')
    self._ena = ENASCPI(self._ena_ip)
    # Check if this is an expected ENA.
    ena_sn = self._ena.GetSerialNumber()
    logging.info('Connected to ENA %s.', ena_sn)
    # Check if this SN is in the whitelist.
    ena_whitelist = self._config['network']['ena_mapping'][self._ena_ip]
    if ena_sn not in ena_whitelist:
      self._ena.Close()
      raise ValueError('ENA %s is not in the while list.' % ena_sn)
    self._ena_name = ena_whitelist[ena_sn]
    logging.info('The ENA is now identified as %r.', self._ena_name)

  def _DownloadParametersFromShopfloor(self):
    """Downloads parameters from shopfloor."""
    logging.info('Downloading parameters from shopfloor...')
    caches_dir = os.path.join(CACHES_DIR, 'parameters')
    DownloadParameters([self.args.config_path], caches_dir)
    logging.info('Parameters downloaded.')
    # Parse and load parameters.
    self._LoadConfig(os.path.join(caches_dir, self.args.config_path))

  def _ResetDataForNextTest(self):
    """Resets internal data for the next testing cycle."""
    self._log_to_file = StringIO.StringIO()
    self._raw_traces = {}
    self._vswr_detail_results = {}
    self._iteration_hash = str(uuid.uuid4())
    self._results = {name: TestState.UNTESTED for name in self._RESULT_IDS}
    logging.info('Reset internal data.')

  def _LoadConfig(self, config_path):
    """Reads the configuration from a file."""
    logging.info('Loading config from %s...', config_path)
    self._config = yaml.load(open(config_path).read())
    # Load shopfloor related settings.
    self._path_name = self._config.get('path_name', 'UnknownPath')
    shopfloor_config = self._config.get('shopfloor', {})
    self._shopfloor_enabled = shopfloor_config.get('enabled', False)
    self._shopfloor_timeout = shopfloor_config.get('timeout', 15)
    self._shopfloor_ignore_on_fail = shopfloor_config.get('ignore_on_fail')
    self._max_iterations = self._config.get('max_iterations', None)
    logging.info('Config %s loaded.', self._config.get('annotation'))

  def _SetUSBPath(self, usb_path):
    """Updates the USB device path."""
    self._usb_path = usb_path
    logging.info('Found USB path %s', self._usb_path)

  def _LoadParametersFromUSB(self):
    """Loads parameters from USB."""
    with MountedMedia(self._usb_path, 1) as config_root:
      config_path = os.path.join(config_root, self.args.config_path)
      self._LoadConfig(config_path)

  def _RaiseUSBRemovalException(self, unused_event):
    """Prevents unexpected USB removal."""
    raise Exception('USB removal is not allowed during test.')

  def _LoadSNSpecificParameters(self):
    """Loads parameters for a specific serial number from the matched config."""
    self._sn_config_name = self._sn_config.get('config_name')
    self._take_screenshot = self._sn_config.get('take_screenshot', False)
    self._reference_info = self._sn_config.get('reference_info', False)
    self._marker_info = self._sn_config.get('set_marker', None)
    self._sweep_restore = self._sn_config.get('sweep_restore', None)
    self._vswr_threshold = {
        'cell': self._sn_config['cell_vswr_threshold'],
        'wifi': self._sn_config['wifi_vswr_threshold']}

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
    def _GetConfigForSerialNumber():
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
      for sn_config in self._config['serial_specific_configuration']:
        sn_config_name = sn_config.get('config_name')
        if not sn_config_name:
          raise Exception('Config name does not exist.')
        sn_regex = sn_config.get('sn_regex')
        if not sn_regex:
          raise Exception("Regexp doesn't exist in config %s." % sn_config_name)
        if re.search(sn_regex, self._serial_number):
          logging.info('SN matched config %s.', sn_config_name)
          return sn_config
      return None

    # Reset SN input box and hide error message.
    self._ui.RunJS('$("sn").value = ""')
    self._ui.RunJS('$("sn-format-error").style.display = "none"')
    self._ShowMessageBlock('enter-sn')
    # Loop until the right serial number has been entered.
    while True:
      # Focus and select the text for convenience.
      self._ui.RunJS('$("sn").select()')
      self._WaitForKey(test_ui.ENTER_KEY)
      self._serial_number = self._GetSN()
      self._sn_config = _GetConfigForSerialNumber()
      if self._sn_config:
        return
      else:
        self._ui.RunJS('$("sn-format-error-value").innerHTML = "%s"' %
                       self._serial_number)
        self._ui.RunJS('$("sn-format-error").style.display = ""')

  def _GetTraces(self, freqs_in_mhz, parameters, purpose='unspecified'):
    """Wrapper for GetTraces in order to log details.

    Args:
      freqs_in_mhz: an iterable container of frequencies to acquire.
      parameters: the type of trace to acquire, e.g., 'S11', 'S22', etc.
          Detailed in GetTraces().
      purpose: additional tag for detailed logging.

    Returns:
      Current traces from the ENA.
    """
    # Generate the sweep tuples.
    freqs = sorted(freqs_in_mhz)
    segments = [(freq_min * 1e6, freq_max * 1e6, 2) for
                freq_min, freq_max in zip(freqs, freqs[1:])]

    self._ena.SetSweepSegments(segments)
    ret = self._ena.GetTraces(parameters)
    self._raw_traces[purpose] = ret
    return ret

  def _CaptureScreenshot(self, filename_prefix):
    """Captures the screenshot based on the settings.

    Screenshot will be saved in 3 places: ENA, USB disk, and shopfloor (if
    shopfloor is enabled). Timestamp will be automatically added as postfix to
    the output name.

    Args:
      filename_prefix: prefix for the image file name.
    """
    # Save a screenshot copy in ENA.
    filename = '%s[%s]' % (
        filename_prefix, TimeString(time_separator='-', milliseconds=False))
    self._ena.SaveScreen(filename)

    # The SaveScreen above has saved a screenshot inside ENA, but it does not
    # allow reading that file directly (see SCPI protocol for details). To save
    # a copy locally, we need to make another screenshot using ENA's HTTP
    # service (image.asp) which always puts the file publicly available as
    # "disp.png".
    logging.info('Requesting ENA to generate screenshot')
    urllib.urlopen('http://%s/image.asp' % self._ena_ip).read()
    png_content = urllib.urlopen('http://%s/disp.png' % self._ena_ip).read()
    Log('vswr_screenshot',
        ab_serial_number=self._serial_number,
        path=self._path_name,
        filename=filename)

    with file_utils.UnopenedTemporaryFile() as temp_png_path:
      with open(temp_png_path, 'w') as f:
        f.write(png_content)

      # Save screenshot to USB disk.
      formatted_date = time.strftime('%Y%m%d', time.localtime())
      logging.info('Saving screenshot to USB under dates %s', formatted_date)
      with MountedMedia(self._usb_path, 1) as mount_dir:
        target_dir = os.path.join(mount_dir, formatted_date, 'screenshot')
        TryMakeDirs(target_dir)
        filename_in_abspath = os.path.join(target_dir, filename)
        shutil.copyfile(temp_png_path, filename_in_abspath)
        logging.info('Screenshot %s saved in USB.', filename)

      # Save screenshot to shopfloor if needed.
      if self._shopfloor_enabled:
        logging.info('Sending screenshot to shopfloor')
        log_name = os.path.join(self._path_name, 'screenshot', filename)
        self._UploadToShopfloor(
            temp_png_path, log_name,
            ignore_on_fail=self._shopfloor_ignore_on_fail,
            timeout=self._shopfloor_timeout)
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
    min_value = threshold[0]
    max_value = threshold[1]
    difference = max(
        (min_value - extracted_value) if min_value else 0,
        (extracted_value - max_value) if max_value else 0)
    check_pass = (difference <= 0)

    if (not check_pass) and print_on_failure:
      # Highlight the failed freqs in console.
      factory.console.info(
          '%10s failed at %.0f MHz[%9.3f dB], %9.3f dB '
          'away from threshold[%s, %s]',
          title, freq / 1000000.0, float(extracted_value),
          float(difference), min_value, max_value)
    # Record the detail for event_log.
    self._vswr_detail_results['%.0fM' % (freq / 1E6)] = {
        'type': title,
        'freq': freq,
        'observed': extracted_value,
        'result': check_pass,
        'threshold': [min_value, max_value],
        'diff': difference}
    return check_pass

  def _CompareTraces(self, traces, cell_or_wifi, main_or_aux, ena_parameter):
    """Returns the traces and spec are aligned or not.

    It calls the check_measurement for each frequency and records
    coressponding result in eventlog and raw logs.

    Usage example:
        self._test_sweep_segment(traces, 'cell', 1, 'cell_main', 'S11')

    Args:
      traces: Trace information from ENA.
      cell_or_wifi: 'cell' or 'wifi' antenna.
      main_or_aux: 'main' or 'aux' antenna.
      ena_parameter: the type of trace to acquire, e.g., 'S11', 'S22', etc.
          Detailed in ena.GetTraces()
    """
    log_title = '%s_%s' % (cell_or_wifi, main_or_aux)
    self._log_to_file.write(
        'Start measurement [%s], with profile[%s,col %s], from ENA-%s\n' %
        (log_title, cell_or_wifi, main_or_aux, ena_parameter))

    # Generate sweep tuples.
    all_passed = True
    logs = [('Frequency',
             'Antenna-%s' % main_or_aux,
             'ENA-%s' % ena_parameter,
             'Result')]
    for threshold in self._vswr_threshold[cell_or_wifi]:
      freq = threshold['freq'] * 1e6
      standard = (threshold['%s_min' % main_or_aux],
                  threshold['%s_max' % main_or_aux])
      response = traces.GetFreqResponse(freq, ena_parameter)
      passed = self._CheckMeasurement(
          standard, response, print_on_failure=True,
          freq=freq, title=log_title)
      logs.append((freq, standard, response, passed))
      all_passed = all_passed and passed

    self._log_to_file.write(
        '%s results:\n%s\n' % (log_title, pprint.pformat(logs)))
    Log('vswr_%s' % log_title,
        ab_serial_number=self._serial_number,
        iterations=self._current_iteration,
        iteration_hash=self._iteration_hash,
        current_config_name=self._sn_config_name,
        ena_name=self._ena_name,
        ena_parameter=ena_parameter,
        config=(log_title, cell_or_wifi, main_or_aux, ena_parameter),
        detail=self._vswr_detail_results)

    return all_passed

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
          'Successfully synced %s in %.03f s',
          description, time.time() - start_time)
    except Exception as e:
      if ignore_on_fail:
        factory.console.info(
            'Failed to sync with shopfloor for [%s], ignored', log_name)
        return False
      else:
        raise e
    return True

  def _TestAntennas(self, main_or_aux):
    """Tests either main or aux antenna for both cellular and wifi.

    Args:
      main_or_aux: str, specify which antenna to test, either 'main' or 'aux'.
    """
    # Get frequencies we want to test.
    freqs = (
        set([f['freq'] for f in self._vswr_threshold['cell']]) |
        set([f['freq'] for f in self._vswr_threshold['wifi']]))
    traces = self._GetTraces(
        freqs, ['S11', 'S22'], purpose=('test_%s_antennas' % main_or_aux))

    # Restore sweep if needed.
    if self._sweep_restore:
      self._ena.SetLinearSweep(self._sweep_restore[0], self._sweep_restore[1])
    # Set marker.
    for marker in self._marker_info:
      self._ena.SetMarker(
          marker['channel'], marker['marker_num'], marker['marker_freq'])
    # Take screenshot if needed.
    if self._take_screenshot:
      self._CaptureScreenshot('[%s]%s' % (main_or_aux, self._serial_number))

    self._results['cell-%s' % main_or_aux] = (
        TestState.PASSED
        if self._CompareTraces(traces, 'cell', main_or_aux, 'S11') else
        TestState.FAILED)
    self._results['wifi-%s' % main_or_aux] = (
        TestState.PASSED
        if self._CompareTraces(traces, 'wifi', main_or_aux, 'S22') else
        TestState.FAILED)

  def _GenerateFinalResult(self):
    """Generates the final result."""
    self._results['final-result'] = (
        TestState.PASSED
        if all(self._results[f] for f in self._RESULTS_TO_CHECK) else
        TestState.FAILED)
    self._log_to_file.write('Result in summary:\n%s\n' %
                            pprint.pformat(self._results))
    Log('vswr_result',
        ab_serial_number=self._serial_number,
        path=self._path_name,
        results=self._results)

  def _SaveLog(self):
    """Saves the logs and writes event log."""
    self._log_to_file.write('\n\nRaw traces:\n%s\n' %
                            pprint.pformat(self._raw_traces))
    Log('vswr_detail',
        ab_serial_number=self._serial_number,
        path=self._path_name,
        raw_trace=self._raw_traces)

    logging.info('Writing log with SN: %s.', self._serial_number)
    with file_utils.UnopenedTemporaryFile() as temp_log_path:
      with open(temp_log_path, 'w') as f:
        f.write(self._log_to_file.getvalue())
      filename = self._serial_number + '.txt'

      # Write log file to USB.
      with MountedMedia(self._usb_path, 1) as mount_dir:
        formatted_date = time.strftime('%Y%m%d', time.localtime())
        target_dir = os.path.join(mount_dir, formatted_date, 'usb')
        TryMakeDirs(target_dir)
        full_path = os.path.join(target_dir, filename)
        shutil.copyfile(temp_log_path, full_path)

      # Upload to shopfloor.
      log_name = os.path.join(self._path_name, 'usb', filename)
      if self._shopfloor_enabled:
        self._UploadToShopfloor(
            temp_log_path, log_name,
            ignore_on_fail=self._shopfloor_ignore_on_fail,
            timeout=self._shopfloor_timeout)

  def _SetUpNetwork(self):
    """Sets up the local network.

    The network config should look like the example below:

      network:
        local_ip: !!python/tuple
        - interface:1
        - 192.168.100.20
        - 255.255.255.0
        ena_mapping:
          192.168.100.1:
            MY99999999: Taipei E5071C-mock
          192.168.132.55:
            MY46107723: Line C VSWR 1
            MY46108580: Line C VSWR 2(tds)
            MY46417768: Line A VSWR 3

    About local_ip: use 'eth1' for a specific interface; or 'interface:1' for
    alias, in which 'interface' will be automatically replaced by the default
    interface. And the ':1' part is just a postfix number to distinguish from
    the original interface. You can choose whatever you like. It means the same
    thing as the ifconfig alias. Please refer to ifconfig's manual for more
    detail.
    """
    logging.info('Setting up network...')
    network_config = self._config['network']

    # Flush route cache just in case.
    Spawn(['ip', 'route', 'flush', 'cache'], check_call=True)
    default_interface = FindUsableEthDevice(raise_exception=True)
    logging.info('Default interface is %s.', default_interface)
    # Use the default interface if local_ip is not given.
    local_ip = network_config['local_ip']
    if local_ip is None:
      interface = default_interface
    else:
      interface, address, netmask = local_ip
      # Try to replace the string to default interface.
      interface = interface.replace('interface', default_interface)
      self._SetLocalIP(interface, address, netmask)
    self._FindENA(interface, network_config['ena_mapping'])

  def _SetLocalIP(self, interface, address, netmask):
    """Sets the interface with specific IP address."""
    logging.info(
        'Set interface %s as %s/%s.', interface, address, netmask)
    Spawn(['ifconfig', interface, address, 'netmask', netmask], check_call=True)
    # Make sure the underlying interface is up.
    Spawn(['ifconfig', interface.split(':')[0], 'up'], check_call=True)

  def _FindENA(self, interface, ena_mapping):
    """Tries to find the available ENA.

    This function adds the route information for each of the possible ENA in
    the mapping list. In addition, check if there's only one ENA in the visible
    scope.

    Args:
      interface: The network interface used. E.g. eth0, eth1:2.
      ena_mapping: ENA config, see doc of self._SetUpNetwork for more info.
    """
    valid_ping_count = 0
    for ena_ip in ena_mapping.iterkeys():
      # Manually add route information for all possible ENAs. Might be
      # duplicated, so ignore the exit code.
      Spawn(['route', 'add', ena_ip, interface], call=True)
      # Flush route cache just in case.
      Spawn(['ip', 'route', 'flush', 'cache'], check_call=True)
      # Ping the host
      logging.info('Searching for ENA at %s...', ena_ip)
      if PingHost(ena_ip, 2) != 0:
        logging.info('Not found at %s.', ena_ip)
      else:
        logging.info('Found ENA at %s.', ena_ip)
        valid_ping_count += 1
        self._ena_ip = ena_ip
    if valid_ping_count != 1:
      raise Exception(
          'Found %d ENAs which should be only 1.' % valid_ping_count)
    logging.info('IP of ENA automatic detected as %s', self._ena_ip)

  def _ShowResults(self):
    """Displays the final result."""
    self._ui.SetHTML(self._serial_number, id='result-serial-number')
    for name in self._RESULT_IDS:
      self._ui.SetHTML(self._results[name], id='result-%s' % name)

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
    self._max_iterations = 0
    self._path_name = ''
    self._usb_path = ''
    self._shopfloor_enabled = False
    self._shopfloor_timeout = 0
    self._shopfloor_ignore_on_fail = False
    self._serial_number = ''
    self._ena = None
    self._ena_name = None
    self._ena_ip = None
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
    self._results = {name: TestState.UNTESTED for name in self._RESULT_IDS}
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
    self._monitor = MediaMonitor()
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
    self._SetUpNetwork()

    self._ShowMessageBlock('connect-to-ena')
    self._ConnectToENA()

    self._ShowMessageBlock('check-calibration')
    self._CheckCalibration()

    self._current_iteration = 0
    while True:
      # Force to quit if max iterations reached.
      self._current_iteration += 1
      if self._max_iterations and (
          self._current_iteration > self._max_iterations):
        factory.console.info('Max iterations reached, please restart.')
        break
      logging.info('Starting iteration %s...', self._current_iteration)

      self._ShowMessageBlock('prepare-panel')
      self._ResetDataForNextTest()
      self._WaitForKey(test_ui.ENTER_KEY)

      self._WaitForValidSN()
      self._LoadSNSpecificParameters()

      self._ShowMessageBlock('prepare-main-antenna')
      self._WaitForKey('A')

      self._ShowMessageBlock('test-main-antenna')
      self._TestAntennas('main')

      self._ShowMessageBlock('prepare-aux-antenna')
      self._WaitForKey('K')

      self._ShowMessageBlock('test-aux-antenna')
      self._TestAntennas('aux')

      self._GenerateFinalResult()

      self._ShowMessageBlock('save-log')
      self._SaveLog()

      self._ShowMessageBlock('show-result')
      self._ShowResults()
      self._WaitForKey(test_ui.ENTER_KEY)
