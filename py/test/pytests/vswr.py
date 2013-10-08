# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import unittest
import uuid
import yaml

from Queue import Queue

from cros.factory.goofy.connection_manager import PingHost
from cros.factory.goofy.goofy import CACHES_DIR
from cros.factory.rf.e5071c_scpi import ENASCPI
from cros.factory.rf.utils import CheckPower, DownloadParameters
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.test.media_util import MediaMonitor, MountedMedia
from cros.factory.utils.net_utils import FindUsableEthDevice
from cros.factory.utils.process_utils import Spawn


class VSWR(unittest.TestCase):
  """A test for antenna modules using fixture Agilent E5017C (ENA).

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
      'sn', 'cell-main', 'cell-aux', 'wifi-main', 'wifi-aux', 'final-result']
  _RESULTS_TO_CHECK = [
      'sn', 'cell-main', 'cell-aux', 'wifi-main', 'wifi-aux']

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
      raise Exception("No calibration data in config file.")
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
    # TODO(littlecvr) Implement this.

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
    logging.info("Found USB path %s", self._usb_path)

  def _LoadParametersFromUSB(self):
    """Loads parameters from USB."""
    with MountedMedia(self._usb_path, 1) as config_root:
      config_path = os.path.join(config_root, self.args.config_path)
      self._LoadConfig(config_path)

  def _RaiseUSBRemovalException(self, dummy_event):
    """Prevents unexpected USB removal."""
    raise Exception("USB removal is not allowed during test.")

  def _LoadSNSpecificParameters(self):
    """Loads parameters for a specific serial number from the matched config."""
    self._sn_config_name = self._sn_config.get('config_name')
    self._auto_screenshot = self._sn_config.get('auto_screenshot', False)
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

  def _TestMainAntennas(self):
    """Tests the main antenna of cellular and wifi."""
    # TODO(littlecvr) Implement this.

  def _TestAuxAntennas(self):
    """Tests the aux antenna of cellular and wifi."""
    # TODO(littlecvr) Implement this.

  def _SaveLog(self):
    """Saves the logs and writes event log."""
    # TODO(littlecvr) Implement this.

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
          "Found %d ENAs which should be only 1." % valid_ping_count)
    logging.info('IP of ENA automatic detected as %s', self._ena_ip)

  def _ShowResults(self):
    """Displays the final result."""
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
    self._auto_screenshot = False
    self._reference_info = False
    self._marker_info = None
    self._sweep_restore = None
    self._vswr_threshold = {}
    # Clear results.
    self._results = {name: TestState.UNTESTED for name in self._RESULT_IDS}

    # Set up UI.
    self._event_queue = Queue()
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

    current_iteration = 0
    while True:
      # Force to quit if max iterations reached.
      current_iteration += 1
      if self._max_iterations and current_iteration > self._max_iterations:
        factory.console.info('Max iterations reached, please restart.')
        break
      logging.info("Starting iteration %s...", current_iteration)

      self._ShowMessageBlock('prepare-panel')
      self._ResetDataForNextTest()
      self._WaitForKey(test_ui.ENTER_KEY)

      self._WaitForValidSN()
      self._LoadSNSpecificParameters()

      self._ShowMessageBlock('prepare-main-antenna')
      self._WaitForKey('A')

      self._ShowMessageBlock('test-main-antenna')
      self._TestMainAntennas()

      self._ShowMessageBlock('prepare-aux-antenna')
      self._WaitForKey('K')

      self._ShowMessageBlock('test-aux-antenna')
      self._TestAuxAntennas()

      self._ShowMessageBlock('save-log')
      self._SaveLog()

      self._ShowMessageBlock('show-result')
      self._ShowResults()
      self._WaitForKey(test_ui.ENTER_KEY)
