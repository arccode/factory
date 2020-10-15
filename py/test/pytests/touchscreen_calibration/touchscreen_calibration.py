# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import collections.abc
from io import StringIO
import os
import re
import threading
import time
import xmlrpc.client

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.fixture.touchscreen_calibration import fixture
from cros.factory.test.i18n import _
from cros.factory.test.pytests.touchscreen_calibration import sensors_server
from cros.factory.test.pytests.touchscreen_calibration import touchscreen_calibration_utils  # pylint: disable=line-too-long
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test.utils import media_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


# __name__ looks like "cros.factory.test.pytests.touchscreen_calibration".
# test_name is "touchscreen_calibration"
test_name = __name__.split('.')[-1]


Event = collections.namedtuple('Event', ['data'])


class Error(Exception):
  def __init__(self, msg):
    session.console.error(msg)
    super(Error, self).__init__()


def _CreateXMLRPCSensorsClient(addr=('localhost', 8000)):
  """A helper function to create the xmlrpc client for sensors data."""
  url = 'http://%s:%s' % addr
  proxy = xmlrpc.client.ServerProxy(url)
  return proxy


class TouchscreenCalibration(test_case.TestCase):
  """Handles the calibration and controls the test fixture."""
  version = 1

  DELTAS = 'deltas'
  REFS = 'refs'
  TRX_OPENS = 'trx_opens'
  TRX_GND_SHORTS = 'trx_gnd_shorts'
  TRX_SHORTS = 'trx-shorts'

  PHASE_SETUP_ENVIRONMENT = 'PHASE_SETUP_ENVIRONMENT'
  PHASE_REFS = 'PHASE_REFS'
  PHASE_DELTAS_UNTOUCHED = 'PHASE_DELTAS_UNTOUCHED'
  PHASE_DELTAS_TOUCHED = 'PHASE_DELTAS_TOUCHED'
  PHASE_TRX_OPENS = 'PHASE_TRX_OPENS'
  PHASE_TRX_GND_SHORTS = 'PHASE_TRX_GND_SHORTS'
  PHASE_TRX_SHORTS = 'PHASE_TRX_SHORTS'
  PHASE_FLASH_FIRMWARE = 'PHASE_FLASH_FIRMWARE'
  PHASE_CHECK_FIRMWARE_VERSION = 'PHASE_CHECK_FIRMWARE_VERSION'

  ARGS = [
      Arg('shopfloor_ip', str, 'The IP address of the shopfloor', default=''),
      Arg('phase', str, 'The test phase of touchscreen calibration',
          default=''),
      Arg('remote_bin_root', str, 'The remote binary root path', default=''),
      Arg('remote_data_dir', str, 'The remote data directory', default=''),
      Arg('fw_update_tool', str, 'The firmware update tool', default=None),
      Arg('fw_file', str, 'The firmware file', default=None),
      Arg('fw_version', str, 'The firmware version', default=None),
      Arg('fw_config', str, 'The firmware config', default=None),
      Arg('hid_tool', str, 'The hid tool to query version information',
          default=None),
      Arg('tool', str, 'The test tool', default=''),
      Arg('keep_raw_logs', bool, 'Whether to attach the log by Testlog',
          default=True),
  ]

  def setUp(self):
    """Sets up the object."""
    self.dut = device_utils.CreateDUTInterface()
    self._calibration_thread = None
    self.fixture = None
    # Temp hack to determine it is sdb or sdc
    self.dev_path = '/dev/sdb' if os.path.exists('/dev/sdb1') else '/dev/sdc'
    self.dump_frames = 3
    self._monitor_thread = None
    self.query_fixture_state_flag = False
    self._mounted_media_flag = True
    self._local_log_dir = '/var/tmp/%s' % test_name
    self._board = self._GetBoard()
    session.console.info('Get Board: %s', self._board)
    self.sensors = None
    self.start_time = None
    self.sensors_ip = None
    self._ReadConfig()
    self._AssignDirectIPsIfTwoInterfaces()
    self.network_status = self.RefreshNetwork()

    # There are multiple boards running this test now.
    # The log path of a particular board is distinguished by the board name.
    self.aux_log_path = os.path.join('touchscreen_calibration', self._board)
    self._GetSensorService()
    self._ConnectTouchDevice()
    self.log = event_log.Log if self.use_shopfloor else self._DummyLog
    session.console.info('Use shopfloor: %s', str(self.use_shopfloor))
    self.summary_file = None
    self.test_pass = None
    self.min_max_msg = None
    self.num_tx = 0
    self.num_rx = 0
    self.touchscreen_status = False

  def _ReadConfig(self):
    self.config = sensors_server.TSConfig(self._board)
    self.use_sensors_server = (
        self.config.Read('Sensors', 'USE_SENSORS_SERVER') == 'True')
    self.sn_length = int(self.config.Read('Misc', 'SN_LENGTH'))
    self.fake_fixture = self.config.Read('Misc', 'FAKE_FIXTURE') == 'True'
    self.use_shopfloor = (self.config.Read('Misc', 'USE_SHOPFLOOR') == 'True')
    self.sensors_ip = self.config.Read('Sensors', 'SENSORS_IP')
    self.direct_host_ip = self.config.Read('Sensors', 'DIRECT_HOST_IP')
    self.direct_sensors_ip = self.config.Read('Sensors', 'DIRECT_SENSORS_IP')
    self.sensors_port = int(self.config.Read('Sensors', 'SENSORS_PORT'))

  def _SetupEnvironment(self):
    if not self.network_status:
      self.FailTask('Check network status error.')

  def _DummyLog(self, *args, **kwargs):
    pass

  def _GetBoard(self):
    """Get the target board."""
    board_path = os.path.join(os.path.dirname(__file__), 'boards', 'board')
    if os.path.isfile(board_path):
      with open(board_path) as f:
        return f.read().strip()
    return None

  def _GetSensorService(self):
    """Get the Sensors service.

    1st priority: connect to the IP address specified in generic_tsab test list.
                  The sensor server is run on a BB or on a DUT in this case.
    2nd priority: instantiate a local sensor object.
                  The sensor object is run on the same local host of the
                  factory test in this case.
    """

    def _ShowError():
      self.ui.Alert(
          _('Fail to detect the touchscreen.\n'
            'Insert the traveler board, and restart the test.'))

    def _CheckStatus(msg):
      """Check the status of the sensor service."""
      try:
        if self.sensors.CheckStatus():
          session.console.info('Sensors service: %s', msg)
          return
        session.console.info('No Sensors service: %s', msg)
      except Exception as e:
        session.console.info('No Sensors service (%s): %s', e, msg)
      _ShowError()

    if self.use_sensors_server:
      if not self.sensors_ip:
        self.ui.Alert(_('Fail to assign DIRECT_SENSORS_IP in ryu.conf'))
        raise Error('Failed to assign sensors_ip.')

      # Connect to the sensors_server at the IP address.
      server_addr = (self.sensors_ip, self.sensors_port)
      self.sensors = _CreateXMLRPCSensorsClient(addr=server_addr)
      self.sensors.PreTest()
      _CheckStatus(str(server_addr))
    else:
      # Instantiate a local sensor object.
      board_sensors = sensors_server.GetSensorServiceClass(self._board)
      self.sensors = board_sensors(
          self.sensors_ip, self.dut,
          remote_bin_root=self.args.remote_bin_root,
          remote_data_dir=self.args.remote_data_dir,
          tool=self.args.tool,
          fw_update_tool=self.args.fw_update_tool,
          hid_tool=self.args.hid_tool,
          fw_file=self.args.fw_file,
          install_flag=(self.args.phase == self.PHASE_SETUP_ENVIRONMENT),
          log=session.console)
      _CheckStatus('Use local sensors object.')

  def _AlertFixtureDisconnected(self):
    """Alerts that the fixture is disconnected."""
    self.ui.Alert(_('Disconnected from controller'))
    self.ui.CallJSFunction('setControllerStatus', self.fixture is not None)

  def _CheckFixtureConnection(self):
    """Check if the fixture is still connected."""
    if not self.fixture:
      self._AlertFixtureDisconnected()
      raise fixture.FixtureException('Fixture disconnected.')

  def _CheckFixtureStateUp(self):
    """Check if the fixture probe is in the UP state."""
    self._CheckFixtureConnection()

    if not self.fixture.IsStateUp():
      self.ui.Alert(_('Probe not in initial position, aborted'))
      raise fixture.FixtureException('Fixture not in UP position.')

  def ReadTest(self):
    """Reads the raw sensor data.."""
    if self.sensors:
      data = self.sensors.Read(self.DELTAS)
      session.console.info('Get data %s', data)
      self.ui.CallJSFunction('displayDebugData', data)
    else:
      session.console.info('No sensors service found.')

  def ProbeSelfTest(self):
    """Execute the probe self test to confirm the fixture works properly."""
    self._CheckFixtureStateUp()
    self.DriveProbeDown()
    self.DriveProbeUp()

  def RefreshFixture(self):
    """Refreshes the fixture."""
    try:
      if self.fake_fixture:
        self.fixture = fixture.FakeFixture(self.ui, state='i')
      else:
        self.fixture = fixture.FixtureSerialDevice()

      if not self.fixture:
        raise fixture.FixtureException(
            'Fail to create the fixture serial device.')

    except Exception as e:
      session.console.info('Refresh fixture serial device exception, %s', e)
      self.ui.Alert(
          _('Please check if the USB cable has been connected '
            'between the test fixture and the control host.\n'
            'Click "RefreshFixture" button on screen after connecting '
            'the USB cable.'))
      self.fixture = None

    fixture_ready = bool(self.fixture) and not self.fixture.IsEmergencyStop()
    self.ui.CallJSFunction('setControllerStatus', fixture_ready)

    if self.fixture and self.fixture.IsEmergencyStop():
      self.ui.Alert(
          _('The test fixture is not ready.\n'
            '(1) It is possible that the test fixure is not powered on yet.\n'
            '    Turn on the power and click "RefreshFixture" button '
            'on screen.\n'
            '(2) The test fixture is already powered on. '
            'The fixture may be in the emergency stop state.\n'
            '    Press debug button on the test fixture and '
            'click "RefreshFixture" button on screen.'))
    self._CreateMonitorPort()

  def RefreshTouchscreen(self):
    """Refreshes all possible saved state for the old touchscreen.

    This functions is called whenever an old touchscreen panel
    removed and a new one attached and awaiting for testing.
    After old states of previous touchscreen panel are cleared and
    new panel detected, show the sign on UI.
    """
    if self.args.phase == self.PHASE_SETUP_ENVIRONMENT:
      self.touchscreen_status = False
      try:
        if self.sensors.CheckStatus():
          self.num_tx, self.num_rx = self.sensors.GetSensorDimensions()
          self.touchscreen_status = True
          session.console.info('touchscreen exists')
        else:
          session.console.info('touchscreen does not exist')
      except Exception as e:
        session.console.info('Exception at refreshing touch screen: %s', e)
      finally:
        state.DataShelfSetValue('touchscreen_status', self.touchscreen_status)
        state.DataShelfSetValue('num_tx', self.num_tx)
        state.DataShelfSetValue('num_rx', self.num_rx)
    else:
      self.touchscreen_status = state.DataShelfGetValue('touchscreen_status')
      self.num_tx = state.DataShelfGetValue('num_tx')
      self.num_rx = state.DataShelfGetValue('num_rx')

    session.console.info('tx = %d, rx = %d', self.num_tx, self.num_rx)
    self.ui.CallJSFunction('setTouchscreenStatus', self.touchscreen_status)
    self.GetSerialNumber()

  def _AssignDirectIPsIfTwoInterfaces(self):
    """Assign direct IPs to the test host and the BB if two network
    interfaces are found.

    There are two legitimate scenarios of configuring the host network.

    Case 1: there is only 1 network interface on the host
      Both the host and the BB connect to the same subnet of the
      shopfloor server and got their IP addresses from a dhcp server.

    Case 2: there are exactly 2 network interfaces on the host
      The host connects to the same subnet of the shopfloor server and
      got their IP addresses from a dhcp server.

      Besides, the host and the BB connects directly to each other in which
      situation the host is assigned DIRECT_HOST_IP and the BB is assigned
      DIRECT_SENSORS_IP. Both DIRECT_HOST_IP and DIRECT_SENSORS_IP are
      defined in the board config file.
    """
    self.host_ip_dict = touchscreen_calibration_utils.NetworkStatus.GetHostIPs()
    if len(self.host_ip_dict) == 2:
      for interface, ip in self.host_ip_dict.items():
        if ip is None:
          cmd = 'ifconfig %s %s' % (interface, self.direct_host_ip)
          if touchscreen_calibration_utils.IsSuccessful(
              touchscreen_calibration_utils.SimpleSystem(cmd)):
            session.console.info('Successfully assign direct host ip: %s',
                                 self.direct_host_ip)
          else:
            raise Error('Failed to assign direct host ip.')
          self.host_ip_dict[interface] = self.direct_host_ip
          self.sensors_ip = self.direct_sensors_ip
        elif ip == self.direct_host_ip:
          self.sensors_ip = self.direct_sensors_ip
    elif len(self.host_ip_dict) > 2:
      msg = 'There should be no more than 2 network interfaces on the host.'
      session.console.error(msg)

  def RefreshNetwork(self):
    """Refreshes all possible saved state for the touchscreen."""
    if self.args.phase == self.PHASE_SETUP_ENVIRONMENT:
      network_status = touchscreen_calibration_utils.NetworkStatus(
          self.sensors_ip, self.args.shopfloor_ip)
      if self.use_sensors_server:
        bb_status = self.sensors_ip if network_status.PingBB() else False
      else:
        bb_status = 'Not used'

      if self.use_shopfloor:
        shopfloor_status = (self.args.shopfloor_ip
                            if network_status.PingShopfloor() else False)
      else:
        shopfloor_status = 'Skipped for debugging'

      state.DataShelfSetValue('bb_status', bb_status)
      state.DataShelfSetValue('shopfloor_status', shopfloor_status)
    else:
      bb_status = state.DataShelfGetValue('bb_status')
      shopfloor_status = state.DataShelfGetValue('shopfloor_status')

    session.console.info('host_ips: %s', str(self.host_ip_dict))
    session.console.info('bb_status: %s', bb_status)
    session.console.info('shopfloor_status: %s', shopfloor_status)
    self.ui.CallJSFunction('setHostNetworkStatus',
                           str(list(self.host_ip_dict.values())))
    self.ui.CallJSFunction('setBBNetworkStatus', bb_status)
    self.ui.CallJSFunction('setShopfloorNetworkStatus', shopfloor_status)

    return (bool(self.host_ip_dict) and
            (not self.use_shopfloor or shopfloor_status) and
            (not self.sensors_ip or bb_status))

  def DriveProbeDown(self):
    """A wrapper to drive the probe down."""
    try:
      self.fixture.DriveProbeDown()
    except Exception:
      self.ui.Alert(_('Probe not in the DOWN position, aborted'))
      raise

  def DriveProbeUp(self):
    """A wrapper to drive the probe up."""
    try:
      self.fixture.DriveProbeUp()
    except Exception:
      self.ui.Alert(_('Probe not in the UP position, aborted'))
      raise

  def _ExecuteCommand(self, command, fail_msg='Failed: '):
    """Execute a command."""
    try:
      os.system(command)
    except Exception as e:
      session.console.warn('%s: %s', fail_msg, e)

  def _CommandOutputSearch(self, command_str, pattern_str, pattern_flags):
    """Execute the command and search the pattern from its output."""
    re_pattern = re.compile(pattern_str, pattern_flags)
    for line in process_utils.SpawnOutput(command_str.split(),
                                          log=True).splitlines():
      output = re_pattern.search(line)
      if output:
        return output.group(1)
    return None

  def Shutdown(self):
    """Shut down the host."""
    self._ExecuteCommand('shutdown -H 0',
                         fail_msg='Failed to shutdown the host')

  def _AttachLog(self, log_name, log_data):
    """Attachs the data by Testlog."""
    if self.args.keep_raw_logs:
      testlog.AttachContent(
          content=log_data,
          name=log_name,
          description='plain text log of %s' % log_name)

  def _WriteLog(self, filename, content):
    """Writes the content to the file and display the message in the log.

    Args:
      filename: the name of the file to write the content to
      content: the content to be written to the file
    """
    def _AppendLog(log_dir, filename, content):
      """Append the content to the filename in the log_dir."""
      with open(os.path.join(log_dir, filename), 'a') as f:
        f.write(content)
      session.console.info('Log written to "%s/%s".', log_dir, filename)

    if self._mounted_media_flag:
      with media_utils.MountedMedia(self.dev_path, 1) as mount_dir:
        _AppendLog(mount_dir, filename, content)
    else:
      _AppendLog(self._local_log_dir, filename, content)

  def _WriteSensorDataToFile(self, logger, sn, phase, test_pass, data):
    """Writes the sensor data and the test result to a file."""
    logger.write('%s: %s %s\n' % (phase, sn, 'Pass' if test_pass else 'Fail'))
    for row in data:
      if isinstance(row, collections.abc.Iterable):
        logger.write(' '.join([str(val) for val in row]))
        logger.write('\n')
      else:
        logger.write('%s\n' % str(row))
    self._WriteLog(sn, logger.getvalue())

  def _GetTime(self):
    """Get the time format like 2014_1225.10:35:20"""
    return time.strftime('%Y_%m%d.%H:%M:%S')

  def _CheckSerialNumber(self, sn):
    """Check if the serial number is legitimate."""
    # This is for development purpose.
    if sn == '0000':
      return True

    if len(sn) != self.sn_length:
      self.ui.Alert(_('Wrong serial number!'))
      return False
    return True

  def _UpdateSummaryFile(self, sn, summary_line):
    """Write the summary line to the summary file of the serial number.

    If a device is tested multiple times, the summary lines are accumulated.
    The summary file on the local host is updated and it will be attached by
    Testlog in FinishTest.
    """
    self.summary_file = 'summary_%s.txt' % sn
    if summary_line.strip():
      summary_line += '  (time: %s)\n' % self._GetTime()
    self._WriteLog(self.summary_file, summary_line)

  def _ReadAndVerifyTRxData(self, sn, phase, category, verify_method):
    # Get data based on the category, i.e., REFS or DELTAS.
    data = self.sensors.ReadTRx(category)
    self.ui.CallJSFunction('displayDebugData', data)
    session.console.debug('%s: get %s data: %s', phase, category, data)
    self.Sleep(1)

    # Verifies whether the sensor data is good or not by the verify_method.
    self.test_pass = verify_method(data, category)
    session.console.info('Invoked verify_method: %s', verify_method.func_name)

    # Write the sensor data and the test result to USB stick, the UI,
    # and also to the shop floor.
    log_to_file = StringIO()
    self._WriteSensorDataToFile(log_to_file, sn, phase, self.test_pass, data)
    self.log('touchscreen_calibration', sn=sn, phase=phase,
             test_pass=self.test_pass, sensor_data=str(data))
    testlog.LogParam('phase', phase)
    testlog.LogParam('test_pass', self.test_pass)
    testlog.LogParam('sensor_data', data)
    result = 'pass' if self.test_pass else 'fail'
    self._AttachLog('touchscreen_calibration.log', str(data))
    summary_line = '%s: %s (%s)' % (sn, result, phase)
    self._UpdateSummaryFile(sn, summary_line)

    if not self.test_pass:
      self.FailTask('%s failed' % phase)

  def _ReadAndVerifySensorData(self, sn, phase, category, verify_method):
    # Get data based on the category, i.e., REFS or DELTAS.
    data = self.sensors.Read(category)
    self.ui.CallJSFunction('displayDebugData', data)
    session.console.debug('%s: get %s data: %s', phase, category, data)
    self.Sleep(1)

    # Verifies whether the sensor data is good or not by the verify_method.
    self.test_pass, failed_sensors, min_value, max_value = verify_method(data)
    session.console.info('Invoked verify_method: %s', verify_method.func_name)
    for sensor in failed_sensors:
      session.console.debug('Failed sensor at (%d, %d) value %d', *sensor)
    session.console.info('Number of failed sensors: %d', len(failed_sensors))
    session.console.info('(min, max): (%d, %d)', min_value, max_value)

    # Write the sensor data and the test result to USB stick, the UI,
    # and also to the shop floor.
    log_to_file = StringIO()
    self._WriteSensorDataToFile(log_to_file, sn, phase, self.test_pass, data)
    self.log('touchscreen_calibration', sn=sn, phase=phase,
             test_pass=self.test_pass, sensor_data=str(data))
    testlog.LogParam('phase', phase)
    testlog.LogParam('test_pass', self.test_pass)
    testlog.LogParam('sensor_data', data)
    result = 'pass' if self.test_pass else 'fail'
    self._AttachLog('touchscreen_calibration.log', str(data))
    summary_line = ('%s: %s (%s) [min: %d, max: %d]' %
                    (sn, result, phase, min_value, max_value))
    self._UpdateSummaryFile(sn, summary_line)
    if phase == 'PHASE_DELTAS_TOUCHED':
      self._UpdateSummaryFile(sn, '\n')

    if not self.test_pass:
      msg = '[min, max] of phase %s: [%d, %d]' % (phase, min_value, max_value)
      self.FailTask(msg)

  def _FlashFirmware(self, sn, phase):
    """."""
    fw_file = self.args.fw_file
    test_pass = self.sensors.FlashFirmware(self.args.fw_version,
                                           self.args.fw_config)
    result = 'pass' if test_pass else 'fail'
    summary_line = ('%s: %s (%s) flashed fw %s:%s' %
                    (sn, result, phase, self.args.fw_version,
                     self.args.fw_config))
    self._UpdateSummaryFile(sn, summary_line)
    if test_pass:
      session.console.info('Have flashed %s to %s', fw_file, sn)
    else:
      self.FailTask('Fail to flash firmware: %s' % fw_file)

  def _CheckFirmwareVersion(self, sn, phase):
    """Check whether the firmware version and the config are correct."""
    fw_version, fw_config = self.sensors.ReadFirmwareVersion()
    session.console.info('firmware version  %s:%s', fw_version, fw_config)
    test_pass = (fw_version == self.args.fw_version and
                 fw_config == self.args.fw_config)
    result = 'pass' if test_pass else 'fail'
    summary_line = ('%s: %s (%s) detected base fw %s:%s' %
                    (sn, result, phase, fw_version, fw_config))
    self._UpdateSummaryFile(sn, summary_line)
    if not test_pass:
      self.FailTask(
          'Firmware version failed. Expected %s:%s, but got %s:%s' %
          (self.args.fw_version, self.args.fw_config, fw_version, fw_config))

  def _DoTest(self, sn, phase):
    """The actual calibration method.

    Args:
      sn: the serial number of the touchscreen under test
      phase: the test phase, including PHASE_REFS, PHASE_DELTAS_UNTOUCHED, and
             PHASE_DELTAS_TOUCHED
    """
    session.console.info('Start testing SN %s for phase %s', sn, phase)
    if not self._CheckSerialNumber(sn):
      return

    if phase == self.PHASE_SETUP_ENVIRONMENT:
      self._SetupEnvironment()

    elif phase == self.PHASE_FLASH_FIRMWARE:
      self._FlashFirmware(sn, phase)

    elif phase == self.PHASE_CHECK_FIRMWARE_VERSION:
      self._CheckFirmwareVersion(sn, phase)

    elif phase == self.PHASE_REFS:
      # Dump one frame of the baseline refs data before the probe touches the
      # panel, and verify the uniformity.
      self._ReadAndVerifySensorData(
          sn, phase, self.REFS, self.sensors.VerifyRefs)

    elif phase == self.PHASE_DELTAS_UNTOUCHED:
      # Dump delta values a few times before the probe touches the panel.
      for unused_time in range(self.dump_frames):
        self._ReadAndVerifySensorData(
            sn, phase, self.DELTAS, self.sensors.VerifyDeltasUntouched)

    elif phase == self.PHASE_TRX_OPENS:
      # Read the TRx test data and verify the test result.
      self._ReadAndVerifyTRxData(sn, phase, self.TRX_OPENS,
                                 self.sensors.VerifyTRx)

    elif phase == self.PHASE_TRX_GND_SHORTS:
      # Read the TRx test data and verify the test result.
      self._ReadAndVerifyTRxData(sn, phase, self.TRX_GND_SHORTS,
                                 self.sensors.VerifyTRx)

    elif phase == self.PHASE_TRX_SHORTS:
      # Read the TRx test data and verify the test result.
      self._ReadAndVerifyTRxData(sn, phase, self.TRX_SHORTS,
                                 self.sensors.VerifyTRx)

    elif phase == self.PHASE_DELTAS_TOUCHED:
      # Dump delta values after the probe has touched the panel.
      # This test involves controlling the test fixture.
      self._CheckFixtureStateUp()

      if not self.sensors.PreRead():
        session.console.error('Failed to execute PreRead().')

      self.DriveProbeDown()

      # Wait a while to let the probe touch the panel stably.
      self.Sleep(10 if self.fake_fixture else 1)

      self._ReadAndVerifySensorData(
          sn, phase, self.DELTAS, self.sensors.VerifyDeltasTouched)

      self.DriveProbeUp()

      if not self.sensors.PostRead():
        session.console.error('Failed to execute PostRead().')

  def FinishTest(self):
    """Finish the test and do cleanup if needed.

    This method is invoked only for Ryu to do final calibration.

    Args:
      event: the event that triggers this callback function
    """
    with open(os.path.join(self._local_log_dir, self.summary_file)) as f:
      self._AttachLog('summary.log', f.read())
    self.sensors.PostTest()
    self.fixture.DriveProbeUpDone()

  def _ConnectTouchDevice(self):
    """Make sure that the touch device is connected to the machine and
    the touch kernel module is inserted properly.
    """
    if not self.sensors.CheckStatus():
      # The kernel module is inserted, but the touch device is not connected.
      self.sensors.PostTest()
      self.ui.Alert(
          _('Fail to detect the touchscreen.\n'
            'Insert the traveler board, and restart the test.'))
      return False
    return True

  def _InsertAndDetectTouchKernelModule(self):
    """Insert the touch kernel module and make sure it is detected."""
    if (not self.sensors.kernel_module.Insert() or
        not self.sensors.kernel_module.IsDeviceDetected()):
      self.sensors.kernel_module.Remove()
      session.console.error('Failed to insert the kernel module: %s.',
                            self.sensors.kernel_module.name)
      self.ui.Alert(
          _('Fail to detect the touchscreen.\n'
            'Remove and re-insert the traveler board. And restart the test.'))
      return False
    return True

  def GetSerialNumber(self):
    """Get the DUT's serial number from device data."""
    sn = device_data.GetSerialNumber()
    self.ui.CallJSFunction('fillInSerialNumber', sn)
    self.StartCalibration(Event({'sn': sn}))

  def StartCalibration(self, event):
    """Starts the calibration thread.

    This method is invoked by snEntered() in touchscreen_calibration.js
    after the serial number has been entered.

    Args:
      event: the event that triggers this callback function
    """

    if self._calibration_thread and self._calibration_thread.isAlive():
      self.ui.Alert(_('Current calibration has not completed yet'))
      return

    if not self._ConnectTouchDevice():
      raise Error('Cannot detect the touch device.')

    sn = event.data.get('sn', '')
    if not sn:
      self.ui.Alert(_('Please enter SN first'))
      self.ui.CallJSFunction('displayDebugData', [])
      return

    self._calibration_thread = threading.Thread(target=self._DoTest,
                                                args=[sn, self.args.phase])
    self._calibration_thread.start()

  def _RegisterEvent(self, event):
    """Adds event handlers for various events.

    Args:
      event: the event to be registered in the UI
    """
    assert hasattr(self, event)
    session.console.debug('Registered event %s', event)
    self.event_loop.AddEventHandler(
        event, lambda unused_event: getattr(self, event)())

  def _MakeLocalLogDir(self):
    if not os.path.isdir(self._local_log_dir):
      try:
        os.makedirs(self._local_log_dir)
      except Exception as e:
        msg = 'Failed to create the local log directory %s: %s'
        session.console.warn(msg, self._local_log_dir, e)

  def _CheckMountedMedia(self):
    """Checks the existence of the mounted media."""
    try:
      # Write the test launch time.
      self._WriteLog('touchscreen_calibration_launch.txt',
                     '%s\n' % time.ctime())
    except Exception:
      self._mounted_media_flag = False
      msg = 'Mounted media does not exist. Use %s instead.'
      session.console.warn(msg, self._local_log_dir)
      self._MakeLocalLogDir()
      self._WriteLog('touchscreen_calibration_launch.txt',
                     '%s\n' % time.ctime())

  def QueryFixtureState(self):
    """Query the fixture internal state including all sensor values."""
    if self.fixture.native_usb:
      try:
        self.fixture.native_usb.QueryFixtureState()
        self.query_fixture_state_flag = True
      except Exception as e:
        session.console.warn('Failed to query fixture state: %s', e)

  def _MonitorNativeUsb(self, native_usb):
    """Get the complete state and show the values that are changed."""
    self.ui.CallJSFunction('showProbeState', 'N/A')
    self.QueryFixtureState()
    self.Sleep(0.5)
    while True:
      native_usb.GetState()

      if self.query_fixture_state_flag:
        state_list = native_usb.CompleteState()
        self.query_fixture_state_flag = False
      else:
        state_list = native_usb.DiffState()
      if state_list:
        session.console.info('Internal state:')
        for name, value in state_list:
          if name == 'state':
            try:
              self.ui.CallJSFunction('showProbeState', value)
            except Exception:
              msg = 'Not able to invoke CallJSFunction to show probe state.'
              session.console.warn(msg)
          session.console.info('      %s: %s', name, value)

  def _CreateMonitorPort(self):
    """Create a thread to monitor the native USB port."""
    if self.fixture and self.fixture.native_usb:
      try:
        self._monitor_thread = process_utils.StartDaemonThread(
            target=self._MonitorNativeUsb, args=[self.fixture.native_usb])
      except threading.ThreadError:
        session.console.warn('Cannot start thread for _MonitorNativeUsb()')

  def runTest(self):
    os.environ['DISPLAY'] = ':0'
    self.start_time = self._GetTime()

    self._CheckMountedMedia()

    events = [
        # Events that are emitted from buttons on the factory UI.
        'ReadTest', 'RefreshFixture', 'RefreshTouchscreen', 'ProbeSelfTest',
        'DriveProbeDown', 'DriveProbeUp', 'Shutdown', 'QueryFixtureState',
        'RefreshNetwork',

        # Events that are emitted from other callback functions.
        'FinishTest',
    ]
    for event in events:
      self._RegisterEvent(event)
    self.event_loop.AddEventHandler('StartCalibration', self.StartCalibration)

    self.ui.BindKeyJS('D', 'toggleDebugPanel();')
    self.WaitTaskEnd()
