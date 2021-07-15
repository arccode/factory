# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to verify the functionality of bluetooth device.

Description
-----------
A bluetooth test to detect adapter, scan bluetooth device, check average RSSI
value, and connect with the bluetooth input device.

To run this bluetooth test, the DUT must have at least one bluetooth adapter.

If argument ``scan_devices`` is set, there should be at least one remote
bluetooth device.

If argument ``pair_with_match`` is set, there should be a bluetooth input
device like a mouse.

Test Procedure
--------------
1. Setup a bluetooth input device (like a mouse) if needed.
2. Enable the connection ability of bluetooth on DUT.
3. A prompt message will be displayed on the UI if ``prompt_scan_message`` and
   ``scan_devices`` is set.
4. The bluetooth test will run automatically.

Dependency
----------
- Device API (``cros.factory.device.chromeos.bluetooth``).
- Bluetooth utility (``cros.factory.test.utils.bluetooth_utils``).

Examples
--------
To detect the specified number of bluetooth adapter on DUT, add this in test
list::

  {
    "pytest_name": "bluetooth",
    "args": {
      "expected_adapter_count": 1
    }
  }

To scan remote bluetooth device and try to find at least one deivce whose name
contains 'KEY_WORD'::

  {
    "pytest_name": "bluetooth",
    "args": {
      "scan_devices": true,
      "keyword": "KEY_WORD"
    }
  }

To check the the largest average RSSI among all scanned devices is bigger than
threshold::

  {
    "pytest_name": "bluetooth",
    "args": {
      "scan_devices": true,
      "average_rssi_threshold": -65.0
    }
  }

To pair, connect with, and disconnect with the bluetooth input device::

  {
    "pytest_name": "bluetooth",
    "args": {
      "pair_with_match": true
    }
  }
"""

import contextlib
import glob
import logging
import os
import shutil
import sys
import threading
import time

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import bluetooth_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import sync_utils


INPUT_MAX_RETRY_TIMES = 10
INPUT_RETRY_INTERVAL = 1
RESET_ADAPTER_SLEEP_TIME = 5
READ_BATTERY_MAX_RETRY_TIMES = 10

BATTERY_LEVEL_KEY = 'battery_level'
READ_BATTERY_STEP_1 = 'read_battery_1'
READ_BATTERY_STEP_2 = 'read_battery_2'


def GetCurrentTime():
  """Get the current time."""
  return time.strftime('%Y-%m-%d %H:%M:%S')


def ColonizeMac(mac):
  """ Given a MAC address, normalize its colons.

  Example: ABCDEF123456 -> AB:CD:EF:12:34:56
  """
  mac_no_colons = ''.join(mac.strip().split(':'))
  groups = (mac_no_colons[x:x+2] for x in range(0, len(mac_no_colons), 2))
  return ':'.join(groups)


def GetInputCount():
  """Returns the number of input devices from probing /dev/input/event*."""
  number_input = len(glob.glob('/dev/input/event*'))
  logging.info('Found %d input devices.', number_input)
  return number_input


def WaitForInputCount(expected_input_count, timeout=10):
  """Waits for the number of input devices to reach the given count.

  Args:
    expected_input_count: The number of input devices that determines success.
    timeout: The maximum time in seconds that we will wait.

  Raises:
    type_utils.TimeoutError if timeout.
  """
  def _CheckInputCount():
    return GetInputCount() == expected_input_count

  sync_utils.WaitFor(_CheckInputCount, timeout, poll_interval=0.2)


def _AppendLog(log_file, data):
  """Appends the log file on the local station."""
  if not log_file:
    return

  # Prepend the current timestamp to each line.
  data = ''.join(GetCurrentTime() + ' ' + line + '\n' if line else '\n'
                 for line in data.splitlines())
  log_dir = os.path.dirname(log_file)
  file_utils.TryMakeDirs(log_dir)
  with open(log_file, 'a') as log:
    log.write(data)


class BluetoothTest(test_case.TestCase):
  ARGS = [
      Arg('expected_adapter_count', int,
          'Number of bluetooth adapters on the machine.',
          default=0),
      Arg('manufacturer_id', int,
          'ID of the manufacturer.',
          default=None),
      Arg('detect_adapters_retry_times', int,
          'Maximum retry time to detect adapters.',
          default=10),
      Arg('detect_adapters_interval_secs', int,
          'Interval in seconds between each retry to detect adapters.',
          default=2),
      Arg('read_bluetooth_uuid_timeout_secs', int,
          'Timeout to read bluetooth characteristics via uuid.',
          default=None),
      Arg('scan_devices', bool,
          'Scan bluetooth device.',
          default=False),
      Arg('prompt_scan_message', bool,
          'Prompts a message to tell user to enable remote devices discovery '
          'mode.',
          default=True),
      Arg('keyword', str,
          'Only cares remote devices whose "Name" contains keyword.',
          default=None),
      Arg('average_rssi_threshold', float,
          'Checks the largest average RSSI among scanned device is equal to or '
          'greater than average_rssi_threshold.',
          default=None),
      Arg('scan_counts', int,
          'Number of scans to calculate average RSSI.',
          default=3),
      Arg('scan_timeout_secs', int,
          'Timeout to do one scan.',
          default=10),
      Arg('input_device_mac', str,
          'The mac address of bluetooth input device.',
          default=None),
      Arg('input_device_mac_key', str,
          'A key for factory shared data containing the mac address.',
          default=None),
      Arg('input_device_rssi_key', str,
          'A key for factory shared data containing the rssi value.',
          default=None),
      Arg('firmware_revision_string_key', str,
          'A key of factory shared data containing firmware revision string.',
          default=None),
      Arg('firmware_revision_string', str,
          'The firmware revision string.',
          default=None),
      Arg('average_rssi_lower_threshold', (float, dict),
          'Checks the average RSSI of the target mac is equal to or '
          'greater than this threshold.',
          default=None),
      Arg('average_rssi_upper_threshold', (float, dict),
          'Checks the average RSSI of the target mac is equal to or '
          'less than this threshold.',
          default=None),
      Arg('pair_with_match', bool,
          'Whether to pair with the strongest match.',
          default=False),
      Arg('finish_after_pair', bool,
          'Whether the test should end immediately after pairing completes.',
          default=False),
      Arg('unpair', bool,
          'Whether to unpair matching devices instead of pair.',
          default=False),
      Arg('check_shift_pair_keys', bool,
          'Check if shift-p-a-i-r keys are pressed.',
          default=False),
      Arg('check_battery_charging', bool,
          'Whether to check if the battery is charging.',
          default=False),
      Arg('read_battery_level', int,
          'Read the battery level.',
          default=None),
      Arg('check_battery_level', bool,
          'Whether to check the battery level.',
          default=False),
      Arg('prompt_into_fixture', bool,
          'Prompt the user to place the base into the test fixture.',
          default=False),
      Arg('use_charge_fixture', bool,
          'Whether a charge fixture is employed.',
          default=False),
      Arg('reset_fixture', bool,
          'Whether to reset the fixture.',
          default=False),
      Arg('start_charging', bool,
          'Prompt the user to start charging the base.',
          default=False),
      Arg('enable_magnet', bool,
          'Enable the base.',
          default=False),
      Arg('reset_magnet', bool,
          'Reset the base.',
          default=False),
      Arg('stop_charging', bool,
          'Prompt the user to stop charging the base.',
          default=False),
      Arg('base_enclosure_serial_number', str,
          'The base enclosure serial number.',
          default=None),
      Arg('battery_log', str,
          'The battery log file.',
          default=None),
      Arg('expected_battery_level', int,
          'The expected battery level.',
          default=100),
      Arg('log_path', str,
          'The directory of the log on the local test host.',
          default=None),
      Arg('keep_raw_logs', bool,
          'Whether to attach the log by Testlog.',
          default=True),
      Arg('test_host_id_file', str,
          'The file storing the id of the test host.',
          default=None),
  ]

  def GetInputDeviceMac(self):
    """Gets the input device MAC to pair with, or None if None

    This may be specified in the arguments, or computed at scan time.
    """
    if self._input_device_mac:
      return self._input_device_mac
    return self._strongest_rssi_mac

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)

    self._strongest_rssi_mac = None
    if self.args.input_device_mac_key:
      self._input_device_mac = (
          ColonizeMac(state.DataShelfGetValue(self.args.input_device_mac_key)))
    else:
      self._input_device_mac = self.args.input_device_mac

    self.btmgmt = bluetooth_utils.BtMgmt(self.args.manufacturer_id)
    self.btmgmt.PowerOn()
    self.hci_device = self.btmgmt.GetHciDevice()
    self.host_mac = self.btmgmt.GetMac()
    logging.info('manufacturer_id %s: %s %s',
                 self.args.manufacturer_id, self.hci_device, self.host_mac)
    self.log_file = None
    self.log_tmp_file = None

    if self.args.base_enclosure_serial_number:
      self.log_tmp_file = file_utils.CreateTemporaryFile()

      if (self.args.test_host_id_file and
          os.path.isfile(self.args.test_host_id_file)):
        with open(self.args.test_host_id_file) as f:
          test_host_id = f.read().strip()
      else:
        test_host_id = None

      filename = '.'.join([self.args.base_enclosure_serial_number,
                           str(test_host_id)])
      if self.args.log_path:
        self.log_file = os.path.join(self.args.log_path, filename)

    self.fixture = None
    if self.args.use_charge_fixture:
      # Import this module only when a test station needs it.
      # A base SMT test station does not need to use the charge fixture.
      # pylint: disable=no-name-in-module
      from cros.factory.test.fixture import base_charge_fixture
      # Note: only reset the fixture in InitializeFixture test.
      #       This will stop charging and disable the magnet initially.
      #       For the following tests, do not reset the fixture so that
      #       the charging could be continued across tests in the test list
      #       defined in the base_host. The purpose is to keep charging the
      #       battery while executing other tests.
      self.fixture = base_charge_fixture.BaseChargeFixture(
          reset=self.args.reset_fixture)

    if self.args.expected_adapter_count:
      self.AddTask(self.DetectAdapter, self.args.expected_adapter_count)

    if self.args.scan_devices:
      if self.args.prompt_scan_message:
        self.AddTask(self.WaitKeyPressed,
                     _('Enable the connection ability of bluetooth device '
                       'and press Enter'))
      self.AddTask(self.ScanDevices)

    if self.args.input_device_rssi_key:
      self.AddTask(self.DetectRSSIofTargetMAC)

    if self.args.prompt_into_fixture:
      self.AddTask(self.WaitKeyPressed,
                   _('Place the base into the fixture, '
                     'and press the space key on the test host.'),
                   test_ui.SPACE_KEY)

    if self.args.read_battery_level == 1:
      self.AddTask(self.ReadBatteryLevel, self._input_device_mac,
                   READ_BATTERY_STEP_1)

    if self.args.enable_magnet and self.args.use_charge_fixture:
      self.AddTask(self.FixtureControl, 'ENABLE_MAGNET')

    if self.args.reset_magnet:
      if self.args.use_charge_fixture:
        self.AddTask(self.FixtureControl, 'DISABLE_MAGNET', post_sleep=1)
        self.AddTask(self.FixtureControl, 'ENABLE_MAGNET')
      else:
        self.AddTask(self.WaitKeyPressed,
                     _('Please re-attach the magnet, '
                       'and press the space key on the test host.'),
                     test_ui.SPACE_KEY)

    if self.args.start_charging:
      if self.args.use_charge_fixture:
        # Let it charge for a little while.
        self.AddTask(self.FixtureControl, 'START_CHARGING')
      else:
        self.AddTask(self.WaitKeyPressed,
                     _('Turn on charging by pressing the green button, '
                       'take the keyboard out and put it back, '
                       'and press the space key on the test host.'),
                     test_ui.SPACE_KEY)

    if self.args.check_shift_pair_keys:
      self.AddTask(self.CheckDisconnectionOfPairedDevice,
                   self._input_device_mac)

    if self.args.unpair:
      self.AddTask(self.Unpair, self._input_device_mac, self.args.keyword)

    if self.args.firmware_revision_string:
      self.AddTask(self.CheckFirmwareRevision, self._input_device_mac)

    if self.args.pair_with_match:
      self.AddTask(self.TestInput, self.args.finish_after_pair)

    if self.args.read_battery_level == 2:
      self.AddTask(self.ReadBatteryLevel, self._input_device_mac,
                   READ_BATTERY_STEP_2)

    if self.args.check_battery_level:
      self.AddTask(self.CheckBatteryLevel)

    if self.args.stop_charging:
      if self.args.use_charge_fixture:
        self.AddTask(self.FixtureControl, 'STOP_CHARGING')
      else:
        self.AddTask(self.WaitKeyPressed,
                     _('Press the green button again to stop charging, '
                       'and press the space key on the test host.'),
                     test_ui.SPACE_KEY)

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam('avg_rssi', ['mac', 'average_rssi'])

  def tearDown(self):
    """Close the charge test fixture."""
    if self.args.use_charge_fixture:
      self.fixture.Close()
    if self.log_file:
      shutil.copyfile(self.log_tmp_file, self.log_file)
    if self.log_tmp_file:
      if self.args.keep_raw_logs:
        testlog.AttachFile(
            path=self.log_tmp_file,
            mime_type='text/plain',
            name='bluetooth.log',
            description='plain text log of bluetooth',
            delete=False)
      os.remove(self.log_tmp_file)

  def WaitKeyPressed(self, message, key=test_ui.ENTER_KEY):
    """Ask operator to turn on bluetooth device and press given key.

    Args:
      message: Html code containing message to show on the screen.
      key: The key to be pressed.
    """
    self.ui.SetState(message)
    logging.info('wait for the user to press key %s', key)
    self.ui.WaitKeysOnce(key)

  def CheckFirmwareRevision(self, mac):
    """A task to read firmware revision string."""
    self.ui.SetState(_('Read firmware revision string.'))

    session.console.info('Begin reading firmware revision string via %s...',
                         self.hci_device)
    try:
      fw = self.RetryWithProgress(
          'reading firmware', INPUT_MAX_RETRY_TIMES, INPUT_RETRY_INTERVAL,
          bluetooth_utils.GattTool.GetDeviceInfo, mac,
          'firmware revision string', hci_device=self.hci_device,
          timeout=self.args.read_bluetooth_uuid_timeout_secs)
    except bluetooth_utils.BluetoothUtilsError as e:
      self.FailTask('Failed to get firmware revision string: %s' % e)

    session.console.info('Expected firmware: %s',
                         self.args.firmware_revision_string)
    session.console.info('Actual firmware: %s', fw)
    state.DataShelfSetValue(self.args.firmware_revision_string_key, fw)

    _AppendLog(self.log_tmp_file, 'FW: %s\n' % fw)

    self.assertEqual(self.args.firmware_revision_string, fw,
                     'Expected firmware: %s, actual firmware: %s' %
                     (self.args.firmware_revision_string, fw))

  def CheckBatteryLevel(self):
    """Checks whether the following conditions are satisfied:

    1. The battery levels are read twice.
    2. battery_level_1 < battery_level_2
    3. battery_level_1 >= expected_battery_level
    """
    self.ui.SetState(
        _('Check if the battery has charged to a higher percentage'))

    battery_level_1 = state.DataShelfGetValue(READ_BATTERY_STEP_1)
    battery_level_2 = state.DataShelfGetValue(READ_BATTERY_STEP_2)
    session.console.info('%s: %s', READ_BATTERY_STEP_1, battery_level_1)
    session.console.info('%s: %s', READ_BATTERY_STEP_2, battery_level_2)

    if not battery_level_1 or not battery_level_2:
      fail_msg = 'Battery levels should be read twice. read_1: %s, read_2: %s'
    elif (battery_level_1 > battery_level_2 or
          (battery_level_1 == battery_level_2 and battery_level_1 < 100)):
      fail_msg = 'Base battery is not charged up. read_1: %s, read_2: %s'
    elif battery_level_1 < self.args.expected_battery_level:
      # Note: battery_level_1 instead of battery_level_2 should be larger than
      #       the expected_battery_level since battery_level_2 is read while
      #       charging and its value is usually larger than its actual value.
      fail_msg = 'Measured battery level %s is less than the expected level %s.'
    else:
      return
    self.FailTask(fail_msg % (battery_level_1, battery_level_2))

  def ReadBatteryLevel(self, mac, step):
    """Read battery level."""
    msg = {
        READ_BATTERY_STEP_1: _('Read battery level for the 1st time.'),
        READ_BATTERY_STEP_2: _('Read battery level for the 2nd time.')
    }[step]

    self.ui.SetState(msg)

    session.console.info('%s via %s ...', step, self.hci_device)
    try:
      battery_level = int(self.RetryWithProgress(
          step, INPUT_MAX_RETRY_TIMES, INPUT_RETRY_INTERVAL,
          bluetooth_utils.GattTool.GetDeviceInfo,
          mac, 'battery level', hci_device=self.hci_device,
          timeout=self.args.read_bluetooth_uuid_timeout_secs))
      session.console.info('%s: %d', step, battery_level)
    except bluetooth_utils.BluetoothUtilsError as e:
      self.FailTask('%s failed to get battery level: %s' % (step, e))

    old_battery_level = state.DataShelfGetValue(step)
    if (step == READ_BATTERY_STEP_1 and
        (old_battery_level is None or battery_level < old_battery_level)):
      # If the battery level at step 1 becomes higher over different rounds
      # (when the operator keeps retesting it for any reasons),
      # we only keep the lowest one. This is because we want to test if the
      # battery could charge to a higher level at step 2 than step 1.
      state.DataShelfSetValue(step, battery_level)
    elif step == READ_BATTERY_STEP_2:
      # We keep the latest battery level read at step 2.
      state.DataShelfSetValue(step, battery_level)

    if step == READ_BATTERY_STEP_1:
      data = '\nSN: %s\nMAC: %s\n' % (self.args.base_enclosure_serial_number,
                                      mac)
    else:
      data = ''
    data += '%s: %s\n' % (step, battery_level)
    _AppendLog(self.log_tmp_file, data)

    if self.args.battery_log:
      with open(self.args.battery_log, 'a') as f:
        f.write('%s %s %s [%s]: %s\n' %
                (GetCurrentTime(), self.args.base_enclosure_serial_number, mac,
                 step, battery_level))

  def FixtureControl(self, operation, post_sleep=0):
    """Control the charge test fixture.

    Args:
      operation: the operation to be performed by the test fixture.
    """
    try:
      # An operation is mapped to its corresponding fixture method defined in
      # base_charge_fixture.BaseChargeFixture class.
      FIXTURE_METHOD_DICT = {'START_CHARGING': 'StartCharging',
                             'STOP_CHARGING': 'StopCharging',
                             'ENABLE_MAGNET': 'EnableMagnet',
                             'DISABLE_MAGNET': 'DisableMagnet'}
      fixture_method = getattr(self.fixture, FIXTURE_METHOD_DICT.get(operation))
      session.console.info('Executing fixture method: %s',
                           fixture_method.__name__)
      fixture_method()
      self.Sleep(post_sleep)
    except Exception as e:
      self.FailTask('error in executing %s (%s)' % (operation, e))

  def DetectAdapter(self, expected_adapter_count):
    """Check number of adapters.

    Detects adapters from dbus and checks if the number of adapters matches the
    expected number.

    Args:
       expected_adapter_count: The expected number of bluetooth adapters.
    """
    self.ui.SetState(_('Detect bluetooth adapter'))
    adapters = self.dut.bluetooth.GetAdapters(
        self.args.detect_adapters_retry_times,
        self.args.detect_adapters_interval_secs)
    self.assertEqual(
        len(adapters), expected_adapter_count,
        'DetectAdapter: expect %d and find %d adapter(s).' %
        (expected_adapter_count, len(adapters)))

  def Unpair(self, device_mac, name_fragment):
    """Unpair from bluetooth devices.

    Args:
      device_mac: None, or the MAC address of the device to unpair.
      name_fragment: None, or substring of the name of the device(s) to unpair.
    """

    def _ShouldUnpairDevice(device_props):
      """Indicate if a device matches the filter, and so should be unpaired.

      If a name fragment or MAC address is given, the corresponding property
      must match. If neither is given, all devices should be unpaired.
      """
      if device_mac is not None and device_props['Address'] != device_mac:
        return False
      if (name_fragment is not None and
          name_fragment not in device_props.get('Name', '')):
        return False
      return device_props['Paired']

    self.ui.SetState(_('Unpairing'))

    input_count_before_unpair = GetInputCount()
    bluetooth_manager = self.dut.bluetooth
    adapter = bluetooth_manager.GetFirstAdapter(self.host_mac)
    devices = bluetooth_manager.GetAllDevices(adapter).values()
    devices_to_unpair = list(filter(_ShouldUnpairDevice, devices))
    logging.info('Unpairing %d device(s)', len(devices_to_unpair))
    for device_to_unpair in devices_to_unpair:
      address = device_to_unpair['Address']
      bluetooth_manager.DisconnectAndUnpairDevice(adapter, address)
      bluetooth_manager.RemovePairedDevice(adapter, address)

    # Check that we unpaired what we thought we did
    expected_input_count = input_count_before_unpair - len(devices_to_unpair)
    WaitForInputCount(expected_input_count)

  def ScanDevices(self):
    """Scan bluetooth devices around.

    In this task, the test will use btmgmt tool to find devices around. The task
    passed if there is at least one device.

    If target_addresses is provided, the test will also check if it can find
    at least one device specified in target_addresses list.

    This sets the strongest matching device mac to self._strongest_rssi_mac.

    Note: this task is intended to be executed on a DUT, i.e., a chromebook, to
    test its bluetooth module. A typical test case is to see if it can detect a
    bluetooth mouse placed around it.
    """

    keyword = self.args.keyword
    average_rssi_threshold = self.args.average_rssi_threshold
    scan_counts = self.args.scan_counts
    timeout_secs = self.args.scan_timeout_secs

    def FilterByKeyword(devices):
      """Returns the devices filtered by keyword.

      If keyword is None, leave devices as it is.
      """
      if keyword is None:
        return devices

      filtered_devices = {}
      for mac, props in devices.items():
        if 'Name' not in props:
          logging.warning('Device %s: %s does not have "Name" property.',
                          mac, props)
          continue

        if keyword in props['Name']:
          filtered_devices[mac] = props
          logging.info('Device %s: "Name" property %s matches keyword %s.',
                       mac, props['Name'], keyword)
      return filtered_devices

    def UpdateRssi(devices_rssis, devices):
      """Updates devices_rssis using RSSI property in devices.

      Args:
        devices_rssis: A dict. Keys are mac addresses and values are lists of
          scanned RSSI value.
        devices: A dict. Keys are mac addresses and values are dicts of
          properties.
      """
      for mac, props in devices.items():
        if 'RSSI' not in props:
          logging.warning('Device %s: %s does not have "RSSI" property.',
                          mac, props)
          continue
        # typecast to str to avoid the weird dbus.String type
        devices_rssis.setdefault(str(mac), []).append(int(props['RSSI']))
      logging.info('UpdateRssi: %s', devices_rssis)

    mac_to_scan = self.GetInputDeviceMac()
    def HasScannedTargetMac():
      """Helper to check if the target MAC has been scanned."""
      return mac_to_scan and mac_to_scan in candidate_rssis

    # Records RSSI of each scan and calculates average rssi.
    candidate_rssis = {}

    for unused_count in range(scan_counts):
      self.ui.SetState(_('Scanning...'))

      with self.TimedProgressBar(timeout_secs):
        devices = self.btmgmt.FindDevices(timeout_secs=timeout_secs)

      logging.info('Found %d device(s).', len(devices))
      for mac, props in devices.items():
        try:
          logging.info('Device found: %s. Name: %s, RSSI: %d',
                       mac, props['Name'], props['RSSI'])
        except KeyError:
          logging.exception('Name or RSSI is not available in %s', mac)

      UpdateRssi(candidate_rssis, FilterByKeyword(devices))
      # Optimization: if we are only interested in one particular address,
      # then we can early-out as soon as we find it
      if average_rssi_threshold is None and HasScannedTargetMac():
        logging.info("Address found, ending scan early")
        break

    logging.info('Found %d candidate device(s) in %s scans.',
                 len(candidate_rssis), scan_counts)
    session.console.info('Candidate devices scan results: %s', candidate_rssis)

    if not candidate_rssis:
      self.FailTask('ScanDevicesTask: Fail to find any candidate device.')

    # Calculates maximum average RSSI.
    max_average_rssi_mac, max_average_rssi = None, -sys.float_info.max
    for mac, rssis in candidate_rssis.items():
      average_rssi = sum(rssis) / len(rssis)
      logging.info('Device %s has average RSSI: %f', mac, average_rssi)
      event_log.Log('avg_rssi', mac=mac, average_rssi=average_rssi)
      with self.group_checker:
        testlog.LogParam('mac', mac)
        testlog.LogParam('average_rssi', average_rssi)
      if average_rssi > max_average_rssi:
        max_average_rssi_mac, max_average_rssi = mac, average_rssi

    logging.info('Device %s has the largest average RSSI: %f',
                 max_average_rssi_mac, max_average_rssi)

    event_log.Log('bluetooth_scan_device', mac=max_average_rssi_mac,
                  rssi=max_average_rssi,
                  meet=max_average_rssi >= average_rssi_threshold)
    testlog.LogParam('max_average_rssi_mac', max_average_rssi_mac)
    testlog.CheckNumericParam('max_average_rssi', max_average_rssi,
                              min=average_rssi_threshold)

    self._strongest_rssi_mac = max_average_rssi_mac

    if mac_to_scan and not HasScannedTargetMac():
      found_addresses = list(candidate_rssis)
      self.FailTask('Failed to find MAC address %s.'
                    'Scanned addresses: %s' % (mac_to_scan, found_addresses))

    if average_rssi_threshold is None:
      # Test is uninterested in RSSI thresholds
      pass
    elif average_rssi_threshold > max_average_rssi:
      session.console.error('The largest average RSSI %f does not meet'
                            ' threshold %f. Please ensure that the test BT '
                            "device is 'visible' and close to the DUT "
                            'antenna.',
                            max_average_rssi, average_rssi_threshold)
      self.FailTask(
          'ScanDeviceTask: The largest average RSSI %f of device %s does'
          ' not meet threshold %f.' %
          (max_average_rssi, max_average_rssi_mac, average_rssi_threshold))
    else:
      session.console.info('The largest average RSSI %f meets threshold %f.',
                           max_average_rssi, average_rssi_threshold)

  def CheckDisconnectionOfPairedDevice(self, device_mac):
    """Check whether a paired device has disconnected.

    Args:
      device_mac: None, or the MAC address of the device to unpair
    """

    def _ConnectedDevice(device_props):
      """Indicates if a connected device matches the device_mac."""
      return (device_props["Address"] == device_mac and
              int(device_props["Connected"]) >= 1)

    def _CheckDisconnection():
      bluetooth_manager = self.dut.bluetooth
      adapter = bluetooth_manager.GetFirstAdapter(self.host_mac)
      devices = bluetooth_manager.GetAllDevices(adapter).values()
      connected_devices = list(filter(_ConnectedDevice, devices))
      logging.info('Connected and paired %d device(s)', len(connected_devices))
      return not connected_devices

    self.ui.SetState(_('Press shift-p-a-i-r simultaneously on the base.'))
    disconnected = self.RetryWithProgress(
        'Check disconnection of the paired base', INPUT_MAX_RETRY_TIMES,
        INPUT_RETRY_INTERVAL, _CheckDisconnection)

    if disconnected:
      msg = 'Shift-P-A-I-R: done'
    else:
      msg = 'Shift-P-A-I-R: not done'

    session.console.info(msg)
    _AppendLog(self.log_tmp_file, msg)

    if not disconnected:
      self.FailTask(msg)

  def DetectRSSIofTargetMAC(self):
    """Detect the RSSI strength at a given target MAC address.

    In this task, a generic test host uses btmgmt tool to find devices around.
    The task passed if it can detect the RSSI strength at the target MAC.

    Note: this task is intended to be executed on a generic test host to test
    if the RSSI of a target device, e.g., a Ryu base, could be detected.
    """

    mac_to_scan = self.GetInputDeviceMac()
    scan_counts = self.args.scan_counts
    timeout_secs = self.args.scan_timeout_secs
    input_device_rssi_key = self.args.input_device_rssi_key

    fail_msg = []
    def _DeriveRSSIThreshold(threshold, fid):
      if isinstance(threshold, (int, float)):
        return threshold
      if isinstance(threshold, dict):
        if fid in threshold:
          return threshold.get(fid)
        fail_msg.append('Fixture ID "%s" is not legitimate!\n' % fid)
      else:
        fail_msg.append('Wrong type of RSSI threshold: %s\n' % threshold)
      return None

    fid = session.GetDeviceID()
    average_rssi_lower_threshold = _DeriveRSSIThreshold(
        self.args.average_rssi_lower_threshold, fid)
    average_rssi_upper_threshold = _DeriveRSSIThreshold(
        self.args.average_rssi_upper_threshold, fid)
    if fail_msg:
      fail_msg = ''.join(fail_msg)
      session.console.error(fail_msg)
      self.FailTask(fail_msg)

    bluetooth_manager = self.dut.bluetooth
    adapter = bluetooth_manager.GetFirstAdapter(self.host_mac)
    logging.info('mac (%s): %s', self.host_mac, adapter)

    rssis = []
    for i in range(1, 1 + scan_counts):
      self.ui.SetState(
          _('Detect RSSI (count {count}/{total})', count=i, total=scan_counts))
      with self.TimedProgressBar(timeout_secs):
        devices = self.btmgmt.FindDevices(timeout_secs=timeout_secs)
      for mac, props in devices.items():
        if mac == mac_to_scan and 'RSSI' in props:
          session.console.info('RSSI of count %d: %.2f', i, props['RSSI'])
          rssis.append(props['RSSI'])

    if not rssis:
      self.FailTask(
          'DetectRSSIofTargetMAC: Fail to get RSSI from device %s.' %
          mac_to_scan)

    average_rssi = sum(rssis) / len(rssis)
    state.DataShelfSetValue(input_device_rssi_key, average_rssi)
    logging.info('RSSIs at MAC %s: %s', mac_to_scan, rssis)
    session.console.info('Average RSSI: %.2f', average_rssi)

    fail_msg = ''
    if (average_rssi_lower_threshold is not None and
        average_rssi < average_rssi_lower_threshold):
      fail_msg += ('Average RSSI %.2f less than the lower threshold %.2f\n' %
                   (average_rssi, average_rssi_lower_threshold))
    if (average_rssi_upper_threshold is not None and
        average_rssi > average_rssi_upper_threshold):
      fail_msg += ('Average RSSI %.2f greater than the upper threshold %.2f' %
                   (average_rssi, average_rssi_upper_threshold))

    # Convert dbus.Int16 in rssis below to regular integers.
    status = (('pass' if fail_msg == '' else 'fail') +
              ' exp: [%.2f, %.2f]' % (average_rssi_lower_threshold,
                                      average_rssi_upper_threshold))
    data = ('Average RSSI: %.2f %s  (%s)\n' %
            (average_rssi, list(map(int, rssis)), status))
    _AppendLog(self.log_tmp_file, data)

    if fail_msg:
      session.console.error(fail_msg)
      self.FailTask(fail_msg)

  def TestInput(self, finish_after_pair):
    """Test bluetooth input device functionality.

    The task will try to pair with the device given by the test,
    and make the connection.
    After the connection, the number of input event should plus one.
    If it does not plus one, the task fails.
    After connection, operator can try to use the input device and press Enter
    to pass checking or Esc to fail the task.
    In the end of test, the task will try to disconnect the device and remove
    the device. If these procedures fail, the task fails.

    Args:
      finish_after_pair: Whether to end the test after pairing. If false,
                         the operator is prompted to test input, and then
                         the device is unpaired.
    """

    def RemoveInput():
      """Disconnects the input device and removes it.

      Returns:
        If disconnection and removal both succeeded, return True, return False
        otherwise.
      """
      return_value = True
      try:
        bt_manager.SetDeviceConnected(adapter, target_mac, False)
        logging.info('Turned off the connection')
      except bt_manager.Error:
        logging.exception('Fail to turn off the connection.')
        return_value = False
      try:
        bt_manager.RemovePairedDevice(adapter, target_mac)
        logging.info('Remove the device')
      except bt_manager.Error:
        logging.exception('Fail to remove the device.')
        return_value = False
      return return_value

    def SaveLogAndFail(fail_reason):
      """Save the fail log and invoke Fail()."""
      data = 'Pairing fail: %s\n' % fail_reason
      _AppendLog(self.log_tmp_file, data)
      self.FailTask(fail_reason)

    def DisplayPasskey(self, passkey):
      logging.info("Displaying passkey %s", passkey)
      self.ui.SetState(
          _('Enter passkey {key} then press enter on the base.', key=passkey))

    def AuthenticationCancelled(self):
      self.ui.SetState(_('Authentication failed, retrying...'))

    need_to_cleanup = True
    try:
      input_count_before_connection = GetInputCount()
      bt_manager = self.dut.bluetooth
      adapter = bt_manager.GetFirstAdapter(self.host_mac)
      target_mac = self.GetInputDeviceMac()
      if not target_mac:
        SaveLogAndFail('InputTestTask: No MAC with which to pair')
      logging.info('Attempting pair with %s', target_mac)

      bt_manager.DisconnectAndUnpairDevice(adapter, target_mac)

      self.ui.SetState(_('Pairing to input device now...'))
      success_create_device = self.RetryWithProgress(
          'create paired device', INPUT_MAX_RETRY_TIMES, INPUT_RETRY_INTERVAL,
          bt_manager.CreatePairedDevice, adapter, target_mac,
          DisplayPasskey, AuthenticationCancelled)
      if not success_create_device:
        SaveLogAndFail('InputTestTask: Fail to create paired device.')

      self.ui.SetState(_('Connecting to input device now...'))
      success_connect_device = self.RetryWithProgress(
          'connect input device', INPUT_MAX_RETRY_TIMES, INPUT_RETRY_INTERVAL,
          bt_manager.SetDeviceConnected, adapter, target_mac, True)
      if not success_connect_device:
        SaveLogAndFail('InputTestTask: Fail to connect device.')

      WaitForInputCount(input_count_before_connection + 1)

      if finish_after_pair:
        # We leave the device paired
        need_to_cleanup = False
        _AppendLog(self.log_tmp_file, 'Pairing finished\n')
        return

      logging.info('InputTestTask: Test the input by operator now')
      self.ui.SetState(
          _('Please test input. Press Escape to fail and Enter to pass'))
      key = self.ui.WaitKeysOnce([test_ui.ENTER_KEY, test_ui.ESCAPE_KEY])
      passed = key == test_ui.ENTER_KEY
      success_to_remove = RemoveInput()
      # No need to cleanup again after the task if removal succeeds here.
      need_to_cleanup = not success_to_remove
      if passed:
        if success_to_remove:
          return
        self.FailTask('InputTestTask: Fail to remove input')
      self.FailTask('Failed by operator')
    finally:
      if need_to_cleanup:
        success_to_remove = RemoveInput()
        if not success_to_remove:
          logging.error('Fail to remove input in Cleanup')

  @contextlib.contextmanager
  def TimedProgressBar(self, timeout_secs):
    """Show timeout on progress bar."""
    self.ui.DrawProgressBar(timeout_secs)

    start_time = time.time()
    stop_event = threading.Event()
    def UpdateProgressBar():
      elapsed_time = time.time() - start_time
      if stop_event.isSet() or elapsed_time >= timeout_secs:
        self.ui.SetProgress(timeout_secs)
        raise StopIteration
      self.ui.SetProgress(elapsed_time)

    self.event_loop.AddTimedHandler(UpdateProgressBar, 0.2, repeat=True)
    try:
      yield
    finally:
      stop_event.set()

  def RetryWithProgress(self, action_string, max_retry_times, retry_interval,
                        target, *args, **kwargs):
    """Runs target function with retries and shows retry times on progress bar.

    Args:
      action_string: The string to describe the action in logging.
      max_retry_times: the maximal retry times.
      retry_interval: the interval between retries.
      target: The target function. *args and **kwargs will be passed to target.

    Returns:
      Return the return value of the target function.
    """
    self.ui.DrawProgressBar(max_retry_times)
    result = None
    for unused_retry in range(max_retry_times):
      try:
        result = target(*args, **kwargs)
      except Exception:
        pass
      self.ui.AdvanceProgress()
      if result:
        break
      self.Sleep(retry_interval)

    self.ui.SetProgress(max_retry_times)
    logging.info('%s was done.' if result else '%s failed.', action_string)
    return result
