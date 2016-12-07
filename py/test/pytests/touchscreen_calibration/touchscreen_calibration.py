# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import collections
import json
import os
import re
import StringIO
import threading
import time
import unittest
import xmlrpclib

import factory_common     # pylint: disable=W0611
import sensors_server

from cros.factory.test.event_log import Log
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test.fixture.touchscreen_calibration.fixture import (
    FixtureException, FakeFixture, FixtureSerialDevice)
from cros.factory.test.test_ui import UI
from cros.factory.test.utils.media_utils import MountedMedia
from cros.factory.utils import process_utils
from cros.factory.utils.arg_utils import Arg
from touchscreen_calibration_utils import (
    IsSuccessful, NetworkStatus, SimpleSystem)


# Temporary file to store stdout for commands executed in this test.
# Note that this file is to be examined only when needed, or just let it
# be overridden.
# Use shopfloor.UploadAuxLogs(_TMP_STDOUT) to upload this file to shopfloor
# server for future process and analyze when needed.
_TMP_STDOUT = '/tmp/stdout.txt'

# __name__ looks like "cros.factory.test.pytests.touchscreen_calibration".
# test_name is "touchscreen_calibration"
test_name = __name__.split('.')[-1]


Event = collections.namedtuple('Event', ['data',])


class Error(Exception):
  def __init__(self, msg):
    factory.console.error(msg)
    super(Error, self).__init__()


def _CreateXMLRPCSensorsClient(addr=('localhost', 8000)):
  """A helper function to create the xmlrpc client for sensors data."""
  url = 'http://%s:%s' % addr
  proxy = xmlrpclib.ServerProxy(url)
  return proxy


class TouchscreenCalibration(unittest.TestCase):
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
      Arg('shopfloor_ip', str, 'The IP address of the shopfloor', ''),
      Arg('phase', str, 'The test phase of touchscreen calibration', ''),
      Arg('remote_bin_root', str, 'The remote binary root path', ''),
      Arg('remote_data_dir', str, 'The remote data directory', ''),
      Arg('fw_update_tool', str, 'The firmware update tool', None),
      Arg('fw_file', str, 'The firmware file', None),
      Arg('fw_version', str, 'The firmware version', None),
      Arg('fw_config', str, 'The firmware config', None),
      Arg('hid_tool', str, 'The hid tool to query version information', None),
      Arg('tool', str, 'The test tool', ''),
  ]

  def setUp(self):
    """Sets up the object."""
    self.dut = device_utils.CreateDUTInterface()
    self._calibration_thread = None
    self.fixture = None
    self.dev_path = None
    self.dump_frames = 0
    self.ui = UI()
    self._monitor_thread = None
    self.query_fixture_state_flag = False
    self._mounted_media_flag = True
    self._local_log_dir = '/var/tmp/%s' % test_name
    self._board = self._GetBoard()
    factory.console.info('Get Board: %s', self._board)
    self.sensors = None
    self.start_time = None
    self.sensors_ip = None
    self._ReadConfig()
    self._AssignDirectIPsIfTwoInterfaces()
    self.network_status = self.RefreshNetwork(None)

    # There are multiple boards running this test now.
    # The log path of a particular board is distinguished by the board name.
    self.aux_log_path = os.path.join('touchscreen_calibration', self._board)
    self._GetSensorService()
    self._ConnectTouchDevice()
    self.log = Log if self.use_shopfloor else self._DummyLog
    factory.console.info('Use shopfloor: %s', str(self.use_shopfloor))
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
    if self.network_status:
      self.ui.Pass()
    else:
      self.ui.Fail('Check network status error.')

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
      msg = ('Fail to detect the touchscreen.\n'
             'Insert the traveler board, and restart the test.\n'
             '无法侦测到面板。\n'
             '请移除小板後再重新插入小板，并重跑测试')
      self.ui.CallJSFunction('showMessage', msg)

    def _CheckStatus(msg):
      """Check the status of the sensor service."""
      try:
        if self.sensors.CheckStatus():
          factory.console.info('Sensors service: %s', msg)
          return
        factory.console.info('No Sensors service: %s', msg)
      except Exception as e:
        factory.console.info('No Sensors service (%s): %s', e, msg)
      _ShowError()

    if self.use_sensors_server:
      if not self.sensors_ip:
        msg = ('Fail to assign DIRECT_SENSORS_IP in ryu.conf\n'
               '需要在 ryu.conf 指定 DIRECT_SENSORS_IP')
        self.ui.CallJSFunction('showMessage', msg)
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
          log=factory.console)
      _CheckStatus('Use local sensors object.')

  def _AlertFixtureDisconnected(self):
    """Alerts that the fixture is disconnected."""
    self.ui.CallJSFunction('showMessage',
                           'Disconnected from controller\n'
                           '与治具失去联系')
    self.ui.CallJSFunction('setControllerStatus', self.fixture is not None)

  def _CheckFixtureConnection(self):
    """Check if the fixture is still connected."""
    if not self.fixture:
      self._AlertFixtureDisconnected()
      raise FixtureException('Fixture disconnected.')

  def _CheckFixtureStateUp(self):
    """Check if the fixture probe is in the UP state."""
    self._CheckFixtureConnection()

    if not self.fixture.IsStateUp():
      self.ui.CallJSFunction('showMessage',
                             'Probe not in initial position, aborted\n'
                             '治具未就原位, 舍弃')
      raise FixtureException('Fixture not in UP position.')

  def ReadTest(self, unused_event):
    """Reads the raw sensor data.."""
    if self.sensors:
      data = self.sensors.Read(self.DELTAS)
      factory.console.info('Get data %s', data)
      data = json.dumps(data)
      self.ui.CallJSFunction('displayDebugData', data)
    else:
      factory.console.info('No sensors service found.')

  def ProbeSelfTest(self, unused_event):
    """Execute the probe self test to confirm the fixture works properly."""
    self._CheckFixtureStateUp()
    self.DriveProbeDown()
    self.DriveProbeUp()

  def RefreshFixture(self, unused_event):
    """Refreshes the fixture."""
    try:
      if self.fake_fixture:
        self.fixture = FakeFixture(self.ui, state='i')
      else:
        self.fixture = FixtureSerialDevice()

      if not self.fixture:
        raise FixtureException('Fail to create the fixture serial device.')

    except Exception as e:
      factory.console.info('Refresh fixture serial device exception, %s', e)
      self.ui.CallJSFunction(
          'showMessage',
          'Please check if the USB cable has been connected '
          'between the test fixture and the control host.\n'
          'Click "RefreshFixture" button on screen after connecting '
          'the USB calbe.\n\n'
          '请确认USB缆线是否已连结制具与控制电脑\n'
          '请连结USB缆线,并点击萤幕上治具连结的刷新按钮。'
      )
      self.fixture = None

    fixture_ready = bool(self.fixture) and not self.fixture.IsEmergencyStop()
    self.ui.CallJSFunction('setControllerStatus', fixture_ready)

    if self.fixture and self.fixture.IsEmergencyStop():
      self.ui.CallJSFunction(
          'showMessage',
          'The test fixture is not ready.\n'
          '(1) It is possible that the test fixure is not powered on yet.\n'
          '    Turn on the power and click "RefreshFixture" button on screen.\n'
          '(2) The test fixture is already powered on. '
          'The fixture may be in the emergency stop state.\n'
          '    Press debug button on the test fixture and '
          'click "RefreshFixture" button on screen.\n\n'
          '治具尚未就位，可能原因如下：\n'
          '(1) 治具电源尚未开启。请开启电源，并点击萤幕上治具连结的刷新按钮。\n'
          '(2) 治具电源已经开启，但是处於紧急停止状态。'
          '请按治具左侧的debug按钮一次。\n'
      )
    self._CreateMonitorPort()

  def RefreshTouchscreen(self, unused_event):
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
          factory.console.info('touchscreen exists')
        else:
          factory.console.info('touchscreen does not exist')
      except Exception as e:
        factory.console.info('Exception at refreshing touch screen: %s', e)
      finally:
        factory.set_shared_data('touchscreen_status', self.touchscreen_status)
        factory.set_shared_data('num_tx', self.num_tx)
        factory.set_shared_data('num_rx', self.num_rx)
    else:
      self.touchscreen_status = factory.get_shared_data('touchscreen_status')
      self.num_tx = factory.get_shared_data('num_tx')
      self.num_rx = factory.get_shared_data('num_rx')

    factory.console.info('tx = %d, rx = %d', self.num_tx, self.num_rx)
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
    self.host_ip_dict = NetworkStatus.GetHostIPs()
    if len(self.host_ip_dict) == 2:
      for interface, ip in self.host_ip_dict.items():
        if ip is None:
          cmd = 'ifconfig %s %s' % (interface, self.direct_host_ip)
          if IsSuccessful(SimpleSystem(cmd)):
            factory.console.info('Successfully assign direct host ip: %s',
                                 self.direct_host_ip)
          else:
            raise Error('Failed to assign direct host ip.')
          self.host_ip_dict[interface] = self.direct_host_ip
          self.sensors_ip = self.direct_sensors_ip
        elif ip == self.direct_host_ip:
          self.sensors_ip = self.direct_sensors_ip
    elif len(self.host_ip_dict) > 2:
      msg = 'There should be no more than 2 network interfaces on the host.'
      factory.console.error(msg)
      return False

  def RefreshNetwork(self, unused_event):
    """Refreshes all possible saved state for the touchscreen."""
    if self.args.phase == self.PHASE_SETUP_ENVIRONMENT:
      network_status = NetworkStatus(self.sensors_ip, self.args.shopfloor_ip)
      if self.use_sensors_server:
        bb_status = self.sensors_ip if network_status.PingBB() else False
      else:
        bb_status = 'Not used'

      if self.use_shopfloor:
        shopfloor_status = (self.args.shopfloor_ip
                            if network_status.PingShopfloor() else False)
      else:
        shopfloor_status = 'Skipped for debugging'

      factory.set_shared_data('bb_status', bb_status)
      factory.set_shared_data('shopfloor_status', shopfloor_status)
    else:
      bb_status = factory.get_shared_data('bb_status')
      shopfloor_status = factory.get_shared_data('shopfloor_status')

    factory.console.info('host_ips: %s', str(self.host_ip_dict))
    factory.console.info('bb_status: %s', bb_status)
    factory.console.info('shopfloor_status: %s', shopfloor_status)
    self.ui.CallJSFunction('setHostNetworkStatus',
                           str(self.host_ip_dict.values()))
    self.ui.CallJSFunction('setBBNetworkStatus', bb_status)
    self.ui.CallJSFunction('setShopfloorNetworkStatus', shopfloor_status)

    return (bool(self.host_ip_dict) and
            (not self.use_shopfloor or shopfloor_status) and
            (not self.sensors_ip or bb_status))

  def DriveProbeDown(self, unused_event=None):
    """A wrapper to drive the probe down."""
    try:
      self.fixture.DriveProbeDown()
    except Exception as e:
      self.ui.CallJSFunction('showMessage',
                             'Probe not in the DOWN position, aborted\n'
                             '治具未就下位, 舍弃')
      raise e

  def DriveProbeUp(self, unused_event=None):
    """A wrapper to drive the probe up."""
    try:
      self.fixture.DriveProbeUp()
    except Exception as e:
      self.ui.CallJSFunction('showMessage',
                             'Probe not in the UP position, aborted\n'
                             '治具未就上位, 舍弃')
      raise e

  def _ExecuteCommand(self, command, fail_msg='Failed: '):
    """Execute a command."""
    try:
      os.system(command)
    except Exception as e:
      factory.console.warn('%s: %s', fail_msg, e)

  def _CommandOutputSearch(self, command_str, pattern_str, pattern_flags):
    """Execute the command and search the pattern from its output."""
    re_pattern = re.compile(pattern_str, pattern_flags)
    for line in process_utils.SpawnOutput(command_str.split(),
                                          log=True).splitlines():
      output = re_pattern.search(line)
      if output:
        return output.group(1)
    return None

  def ShutDown(self, unused_event=None):
    """Shut down the host."""
    self._ExecuteCommand('shutdown -H 0',
                         fail_msg='Failed to shutdown the host')

  def _UploadLog(self, log_name, log_data):
    """Upload the data to shopfloor server as a file."""
    if self.use_shopfloor:
      log_path = os.path.join(self.aux_log_path, log_name)
      shopfloor_client = shopfloor.GetShopfloorConnection()
      shopfloor_client.SaveAuxLog(log_path, xmlrpclib.Binary(log_data))
      factory.console.info('Uploaded sensor data as %s', log_path)

  def _DumpOneFrameToLog(self, logger, category, sn, frame_no):
    """Dumps one frame to log.

    Args:
      logger: the log object
    """
    factory.console.info('... dump_frames %s: %d', category, frame_no)
    data = self.sensors.Read(category)
    logger.write('Dump one frame:\n')
    for row in data:
      logger.write(' '.join([str(val) for val in row]))
      logger.write('\n')

    self.log('touchscreen_calibration_before_touched_%d' % frame_no,
             category=category, sn=sn, sensor_data=str(data))

    log_name = '%s_%s_%s_pre%d' % (self.start_time, sn, category, frame_no)
    self._UploadLog(log_name, str(data))

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
      factory.console.info('Log written to "%s/%s".', log_dir, filename)

    if self._mounted_media_flag:
      with MountedMedia(self.dev_path, 1) as mount_dir:
        _AppendLog(mount_dir, filename, content)
    else:
      _AppendLog(self._local_log_dir, filename, content)

  def _WriteSensorDataToFile(self, logger, sn, phase, test_pass, data):
    """Writes the sensor data and the test result to a file."""
    logger.write('%s: %s %s\n' % (phase, sn, 'Pass' if test_pass else 'Fail'))
    for row in data:
      if isinstance(row, collections.Iterable):
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
      self.ui.CallJSFunction('showMessage', 'Wrong serial number! 序号错误!')
      return False
    return True

  def _UpdateSummaryFile(self, sn, summary_line):
    """Write the summary line to the summary file of the serial number.

    If a device is tested multiple times, the summary lines are accumulated.
    Both the summary files on the local host and on the shopfloor are updated.
    """
    self.summary_file = 'summary_%s.txt' % sn
    if summary_line.strip():
      summary_line += '  (time: %s)\n' % self._GetTime()
    self._WriteLog(self.summary_file, summary_line)
    with open(os.path.join(self._local_log_dir, self.summary_file)) as f:
      self._UploadLog(self.summary_file, f.read())

  def _ReadAndVerifyTRxData(self, sn, phase, category, verify_method):
    # Get data based on the category, i.e., REFS or DELTAS.
    data = self.sensors.ReadTRx(category)
    self.ui.CallJSFunction('displayDebugData', json.dumps(data))
    factory.console.debug('%s: get %s data: %s', phase, category, data)
    time.sleep(1)

    # Verifies whether the sensor data is good or not by the verify_method.
    self.test_pass = verify_method(data, category)
    factory.console.info('Invoked verify_method: %s', verify_method.func_name)

    # Write the sensor data and the test result to USB stick, the UI,
    # and also to the shop floor.
    log_to_file = StringIO.StringIO()
    self._WriteSensorDataToFile(log_to_file, sn, phase, self.test_pass, data)
    self.log('touchscreen_calibration', sn=sn, phase=phase,
             test_pass=self.test_pass, sensor_data=str(data))
    result = 'pass' if self.test_pass else 'fail'
    log_name = '%s_%s_%s_%s' % (sn, self.start_time, phase, result)
    self._UploadLog(log_name, str(data))
    summary_line = '%s: %s (%s)' % (sn, result, phase)
    self._UpdateSummaryFile(sn, summary_line)

    if self.test_pass:
      self.ui.Pass()
    else:
      self.ui.Fail('%s failed' % phase)

  def _ReadAndVerifySensorData(self, sn, phase, category, verify_method):
    # Get data based on the category, i.e., REFS or DELTAS.
    data = self.sensors.Read(category)
    self.ui.CallJSFunction('displayDebugData', json.dumps(data))
    factory.console.debug('%s: get %s data: %s', phase, category, data)
    time.sleep(1)

    # Verifies whether the sensor data is good or not by the verify_method.
    self.test_pass, failed_sensors, min_value, max_value = verify_method(data)
    factory.console.info('Invoked verify_method: %s', verify_method.func_name)
    for sensor in failed_sensors:
      factory.console.debug('Failed sensor at (%d, %d) value %d', *sensor)
    factory.console.info('Number of failed sensors: %d', len(failed_sensors))
    factory.console.info('(min, max): (%d, %d)', min_value, max_value)

    # Write the sensor data and the test result to USB stick, the UI,
    # and also to the shop floor.
    log_to_file = StringIO.StringIO()
    self._WriteSensorDataToFile(log_to_file, sn, phase, self.test_pass, data)
    self.log('touchscreen_calibration', sn=sn, phase=phase,
             test_pass=self.test_pass, sensor_data=str(data))
    result = 'pass' if self.test_pass else 'fail'
    log_name = '%s_%s_%s_%s' % (sn, self.start_time, phase, result)
    self._UploadLog(log_name, str(data))
    summary_line = ('%s: %s (%s) [min: %d, max: %d]' %
                    (sn, result, phase, min_value, max_value))
    self._UpdateSummaryFile(sn, summary_line)
    if phase == 'PHASE_DELTAS_TOUCHED':
      self._UpdateSummaryFile(sn, '\n')

    if self.test_pass:
      self.ui.Pass()
    else:
      msg = '[min, max] of phase %s: [%d, %d]' % (phase, min_value, max_value)
      self.ui.Fail(msg)

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
      factory.console.info('Have flashed %s to %s', fw_file, sn)
      self.ui.Pass()
    else:
      self.ui.Fail('Fail to flash firmware: %s' % fw_file)

  def _CheckFirmwareVersion(self, sn, phase):
    """Check whether the firmware version and the config are correct."""
    fw_version, fw_config = self.sensors.ReadFirmwareVersion()
    factory.console.info('firmware version  %s:%s', fw_version, fw_config)
    test_pass = (fw_version == self.args.fw_version and
                 fw_config == self.args.fw_config)
    result = 'pass' if test_pass else 'fail'
    summary_line = ('%s: %s (%s) detected base fw %s:%s' %
                    (sn, result, phase, fw_version, fw_config))
    self._UpdateSummaryFile(sn, summary_line)
    if test_pass:
      self.ui.Pass()
    else:
      self.ui.Fail(
          'Firmware version failed. Expected %s:%s, but got %s:%s' %
          (self.args.fw_version, self.args.fw_config, fw_version, fw_config))

  def _DoTest(self, sn, phase):
    """The actual calibration method.

    Args:
      sn: the serial number of the touchscreen under test
      phase: the test phase, including PHASE_REFS, PHASE_DELTAS_UNTOUCHED, and
             PHASE_DELTAS_TOUCHED
    """
    factory.console.info('Start testing SN %s for phase %s', sn, phase)
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
      for _ in range(self.dump_frames):
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
        factory.console.error('Failed to execute PreRead().')

      self.DriveProbeDown()

      # Wait a while to let the probe touch the panel stably.
      time.sleep(10 if self.fake_fixture else 1)

      self._ReadAndVerifySensorData(
          sn, phase, self.DELTAS, self.sensors.VerifyDeltasTouched)

      self.DriveProbeUp()

      if not self.sensors.PostRead():
        factory.console.error('Failed to execute PostRead().')

  def FinishTest(self, unused_event):
    """Finish the test and do cleanup if needed.

    This method is invoked only for Ryu to do final calibration.

    Args:
      event: the event that triggers this callback function
    """
    self.sensors.PostTest()
    self.fixture.DriveProbeUpDone()

  def _ConnectTouchDevice(self):
    """Make sure that the touch device is connected to the machine and
    the touch kernel module is inserted properly.
    """
    if not self.sensors.CheckStatus():
      # The kernel module is inserted, but the touch device is not connected.
      self.sensors.PostTest()
      msg = ('Fail to detect the touchscreen.\n'
             'Insert the traveler board, and restart the test.\n'
             '无法侦测到面板。\n'
             '请移除小板後再重新插入小板，并重跑测试')
      self.ui.CallJSFunction('showMessage', msg)
      return False
    return True

  def _InsertAndDetectTouchKernelModule(self):
    """Insert the touch kernel module and make sure it is detected."""
    if (not self.sensors.kernel_module.Insert() or
        not self.sensors.kernel_module.IsDeviceDetected()):
      self.sensors.kernel_module.Remove()
      factory.console.error('Failed to insert the kernel module: %s.',
                            self.sensors.kernel_module.name)
      msg = ('Fail to detect the touchscreen.\n'
             'Remove and re-insert the traveler board. And restart the test.\n'
             '无法侦测到面板。\n'
             '请移除小板後再重新插入小板，并重跑测试')
      self.ui.CallJSFunction('showMessage', msg)
      return False
    return True

  def GetSerialNumber(self, unused_event=None):
    """Get the DUT's serial number from the shopfloor."""
    sn = shopfloor.get_serial_number()
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
      self.ui.CallJSFunction('showMessage',
                             'Current calibration has not completed yet\n'
                             '目前校正尚未结束')
      return

    if not self._ConnectTouchDevice():
      raise Error('Cannot detect the touch device.')

    sn = event.data.get('sn', '')
    if len(sn) == 0:
      self.ui.CallJSFunction('showMessage',
                             'Please enter SN first\n'
                             '请先输入序号')
      self.ui.CallJSFunction('displayDebugData', '[]')
      return

    self._calibration_thread = threading.Thread(target=self._DoTest,
                                                args=[sn, self.args.phase])
    self._calibration_thread.start()

  def _RegisterEvents(self, events):
    """Adds event handlers for various events.

    Args:
      events: the events to be registered in the UI
    """
    for event in events:
      assert hasattr(self, event)
      factory.console.debug('Registered event %s', event)
      self.ui.AddEventHandler(event, getattr(self, event))

  def _MakeLocalLogDir(self):
    if not os.path.isdir(self._local_log_dir):
      try:
        os.makedirs(self._local_log_dir)
      except Exception as e:
        msg = 'Failed to create the local log directory %s: %s'
        factory.console.warn(msg, self._local_log_dir, e)

  def _CheckMountedMedia(self):
    """Checks the existence of the mounted media."""
    try:
      # Write the test launch time.
      self._WriteLog('touchscreen_calibration_launch.txt',
                     '%s\n' % time.ctime())
    except Exception:
      self._mounted_media_flag = False
      msg = 'Mounted media does not exist. Use %s instead.'
      factory.console.warn(msg, self._local_log_dir)
      self._MakeLocalLogDir()
      self._WriteLog('touchscreen_calibration_launch.txt',
                     '%s\n' % time.ctime())

  def QueryFixtureState(self, unused_event=None):
    """Query the fixture internal state including all sensor values."""
    if self.fixture.native_usb:
      try:
        self.fixture.native_usb.QueryFixtureState()
        self.query_fixture_state_flag = True
      except Exception as e:
        factory.console.warn('Failed to query fixture state: %s', e)

  def _MonitorNativeUsb(self, native_usb):
    """Get the complete state and show the values that are changed."""
    self.ui.CallJSFunction('showProbeState', 'N/A')
    self.QueryFixtureState()
    time.sleep(0.5)
    while True:
      native_usb.GetState()

      if self.query_fixture_state_flag:
        state_list = native_usb.CompleteState()
        self.query_fixture_state_flag = False
      else:
        state_list = native_usb.DiffState()
      if state_list:
        factory.console.info('Internal state:')
        for name, value in state_list:
          if name == 'state':
            try:
              self.ui.CallJSFunction('showProbeState', value)
            except Exception:
              msg = 'Not able to invoke CallJSFunction to show probe state.'
              factory.console.warn(msg)
          factory.console.info('      %s: %s', name, value)

  def _CreateMonitorPort(self):
    """Create a thread to monitor the native USB port."""
    if self.fixture and self.fixture.native_usb:
      try:
        self._monitor_thread = process_utils.StartDaemonThread(
            target=self._MonitorNativeUsb, args=[self.fixture.native_usb])
      except threading.ThreadError:
        factory.console.warn('Cannot start thread for _MonitorNativeUsb()')

  def runTest(self, dev_path=None, dump_frames=3):
    """The entry method of the test.

    Args:
      dev_path: the path of the mounted media
      dump_frames: the number of frames to dump before the probe touches panel
    """
    if dev_path is None:
      # Temp hack to determine it is sdb or sdc
      dev_path = '/dev/sdb' if os.path.exists('/dev/sdb1') else '/dev/sdc'
    self.dev_path = dev_path
    self.dump_frames = dump_frames

    os.environ['DISPLAY'] = ':0'
    self.start_time = self._GetTime()

    self._CheckMountedMedia()

    self._RegisterEvents([
        # Events that are emitted from buttons on the factory UI.
        'ReadTest', 'RefreshFixture', 'RefreshTouchscreen', 'ProbeSelfTest',
        'DriveProbeDown', 'DriveProbeUp', 'ShutDown', 'QueryFixtureState',
        'RefreshNetwork',

        # Events that are emitted from other callback functions.
        'StartCalibration', 'FinishTest',
    ])
    self.ui.BindKeyJS('D', 'toggleDebugPanel();')

    self.ui.Run()
