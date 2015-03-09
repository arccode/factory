# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import json
import os
import re
import StringIO
import threading
import time
import unittest
import xmlrpclib

import factory_common     # pylint: disable=W0611
import sysfs_server
import touchscreen_calibration_utils

from cros.factory.test.event_log import Log
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.fixture.touchscreen_calibration.fixture import (
    FixtureException, FakeFixture, FixtureSerialDevice)
from cros.factory.test.media_util import MountedMedia
from cros.factory.test.test_ui import UI
from cros.factory.utils.process_utils import SpawnOutput


# Temporary file to store stdout for commands executed in this test.
# Note that this file is to be examined only when needed, or just let it
# be overridden.
# Use shopfloor.UploadAuxLogs(_TMP_STDOUT) to upload this file to shopfloor
# server for future process and analyze when needed.
_TMP_STDOUT = '/tmp/stdout.txt'

# __name__ looks like "cros.factory.test.pytests.touchscreen_calibration".
# test_name is "touchscreen_calibration"
test_name = __name__.split('.')[-1]


class Error(Exception):
  pass


def _CreateXMLRPCSysfsClient(addr=('localhost', 8000)):
  """A helper function to create the xmlrpc client for sysfs data."""
  url = 'http://%s:%s' % addr
  proxy = xmlrpclib.ServerProxy(url)
  return proxy


class TouchscreenCalibration(unittest.TestCase):
  """Handles the calibration and controls the test fixture."""
  version = 1

  DELTAS = 'deltas'
  REFS = 'refs'

  ARGS = [
      Arg('shopfloor_ip', str, 'The IP address of the shopfloor', ''),
  ]

  def setUp(self):
    """Sets up the object."""
    self._calibration_thread = None
    self.fixture = None
    self.dev_path = None
    self.dump_frames = 0
    self.ui = UI()
    self._monitor_thread = None
    self.query_fixture_state_flag = False
    self._mounted_media_flag = True
    self._local_log_dir = '/var/tmp/%s' % test_name
    self.sysfs_config = sysfs_server.SysfsConfig()
    self.sysfs_ip = self.sysfs_config.Read('Sysfs', 'SYSFS_IP')
    self.sysfs_port = int(self.sysfs_config.Read('Sysfs', 'SYSFS_PORT'))
    self.use_sysfs_server = (
        self.sysfs_config.Read('Sysfs', 'USE_SYSFS_SERVER') == 'True')
    self.delta_lower_bound = int(self.sysfs_config.Read('TouchSensors',
                                                        'DELTA_LOWER_BOUND'))
    self.delta_higher_bound = int(self.sysfs_config.Read('TouchSensors',
                                                         'DELTA_HIGHER_BOUND'))
    self.sn_length = int(self.sysfs_config.Read('Misc', 'SN_LENGTH'))
    self.fake_fixture = self.sysfs_config.Read('Misc', 'FAKE_FIXTURE') == 'True'
    self.use_shopfloor = (
        self.sysfs_config.Read('Misc', 'USE_SHOPFLOOR') == 'True')
    self.network_status = touchscreen_calibration_utils.NetworkStatus(
        self.sysfs_ip, self.args.shopfloor_ip)
    self.sysfs = None
    self.start_time = None
    # TODO(josephsih): samus is the only board for this test so far.
    # When there are more boards later, there should be a method to determine
    # the board name.
    self.aux_log_path = 'touchscreen_calibration/samus'
    self._GetSysfsService()
    self._ConnectTouchDevice()
    self.log = Log if self.use_shopfloor else self._DummyLog
    factory.console.info('Use shopfloor: %s', str(self.use_shopfloor))

  def _DummyLog(self, *args, **kwargs):
    pass

  def tearDown(self):
    self.sysfs.kernel_module.Remove()

  def _GetSysfsService(self):
    """Get the Sysfs servic3.

    1st priority: connect to the IP address specified in generic_tsab test list.
                  The sysfs server is run on a BB or on a DUT in this case.
    2nd priority: instantiate a local sysfs object.
                  The sysfs object is run on the same local host of the
                  factory test in this case.
    """

    def _ShowError():
      msg = ('Fail to detect the touchscreen.\n'
             'Insert the traveler board, and restart the test.\n'
             '无法侦测到面板。\n'
             '请移除小板後再重新插入小板，并重跑测试')
      self.ui.CallJSFunction('showMessage', msg)

    def _CheckStatus(msg):
      """Check the status of sys fs."""
      try:
        if self.sysfs.CheckStatus():
          factory.console.info('Sysfs service: %s', msg)
          return
        factory.console.info('No Sysfs service: %s', msg)
      except Exception as e:
        factory.console.info('No Sysfs service (%s): %s', e, msg)
      _ShowError()

    if not self.sysfs_ip:
      msg = ('No sysfs_ip is assigned.\n'
             'If you intend to run a sysfs_server on another machine, '
             'you need to assign _SYSFS_SERVER_IP in generic_tsab.py.\n'
             'And then do a factory_restart.')
      factory.console.warn(msg)

    if self.use_sysfs_server:
      # Connect to the sysfs_server at the IP address.
      sysfs_addr = (self.sysfs_ip, self.sysfs_port)
      self.sysfs = _CreateXMLRPCSysfsClient(addr=sysfs_addr)
      if not self.sysfs.kernel_module.IsLoaded():
        self.sysfs.kernel_module.Insert()
        time.sleep(1)
      _CheckStatus(str(sysfs_addr))
    else:
      # Instantiate a local sysfs object.
      self.sysfs = sysfs_server.Sysfs(log=factory.console)
      _CheckStatus('local Sysfs object')

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
    if self.sysfs:
      data = self.sysfs.Read(self.DELTAS)
      factory.console.info('Get data %s', data)
      data = json.dumps(data)
      self.ui.CallJSFunction('displayDebugData', data)
    else:
      factory.console.info('No sysfs found')

  def ProbeSelfTest(self, unused_event):
    """Execute the probe self test to confirm the fixture works properly."""
    self._CheckFixtureStateUp()
    self.DriveProbeDown()
    self.DriveProbeUp()

  def RefreshFixture(self, unused_event):
    """Refreshes the fixture."""
    try:
      if self.fake_fixture:
        self.fixture = FakeFixture(state='i')
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
    try:
      if self.sysfs.CheckStatus():
        factory.console.info('touchscreen exist')
        self.ui.CallJSFunction('setTouchscreenStatus', True)
        return
    except Exception as e:
      factory.console.info('Exception at refreshing touch screen: %s', e)
    self.ui.CallJSFunction('setTouchscreenStatus', False)

  def RefreshNetwork(self, unused_event):
    """Refreshes all possible saved state for the old touchscreen.
    """
    host_ip = self.network_status.GetHostIP()
    bb_status = self.network_status.PingBB()
    shopfloor_status = self.network_status.PingShopfloor()
    factory.console.info('shopfloor_status: %s', str(shopfloor_status))
    factory.console.info('shopfloor_ip : %s', self.args.shopfloor_ip)

    self.ui.CallJSFunction('setHostNetworkStatus', str(host_ip))
    self.ui.CallJSFunction('setBBNetworkStatus',
                           bb_status and self.sysfs_ip)
    self.ui.CallJSFunction('setShopfloorNetworkStatus',
                           shopfloor_status and self.args.shopfloor_ip)

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
    for line in SpawnOutput(command_str.split(), log=True).splitlines():
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
    data = self.sysfs.Read(category)
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

  def _WriteSensorDataToFile(self, logger, sn, test_pass, data):
    """Writes the sensor data and the test result to a file."""
    logger.write('%s %s\n' % (sn, 'Pass' if test_pass else 'Fail'))
    for row in data:
      logger.write(' '.join([str(val) for val in row]))
      logger.write('\n')
    self._WriteLog(sn, logger.getvalue())

  def _VerifySensorData(self, data):
    """Determines whether the sensor data is good or not."""
    # There are 3 columns of metal fingers on the probe. The touched_cols are
    # derived through experiments. The values may vary from board to board.
    touched_cols = [1, 35, 69]
    test_pass = True
    for row, row_data in enumerate(data):
      for col in touched_cols:
        value = row_data[col]
        if value < self.delta_lower_bound or value > self.delta_higher_bound:
          factory.console.info('  Failed at (row, col) (%d, %d) value %d',
                               row, col, value)
          test_pass = False
    return test_pass

  def _CheckSerialNumber(self, sn):
    """Check if the serial number is legitimate."""
    # This is for development purpose.
    if sn == '0000':
      return True

    if len(sn) != self.sn_length:
      self.ui.CallJSFunction('showMessage', 'Wrong serial number! 序号错误!')
      return False
    return True

  def _Calibrate(self, sn):
    """The actual calibration method.

    Args:
      sn: the serial number of the touchscreen under test
    """
    self._CheckFixtureStateUp()
    if not self._CheckSerialNumber(sn):
      return

    try:
      factory.console.info('Start calibrating SN %s', sn)
      log_to_file = StringIO.StringIO()

      if not self.sysfs.WriteSysfsSection('PreRead'):
        factory.console.error('Failed to write PreRead section to sys fs.')

      # Dump one frame of the baseline data.
      self._DumpOneFrameToLog(log_to_file, self.REFS, sn, 1)
      time.sleep(0.1)

      # Dump whole frame a few times before probe touches panel.
      for f in range(self.dump_frames):           # pylint: disable=W0612
        self._DumpOneFrameToLog(log_to_file, self.DELTAS, sn, f)
        time.sleep(0.1)

      self.DriveProbeDown()

      # Wait a while to let the probe touch the panel stably.
      time.sleep(1)

      data = self.sysfs.Read(self.DELTAS)
      factory.console.info('Get data %s', data)
      time.sleep(1)

      # Verifies whether the sensor data is good or not.
      test_pass = self._VerifySensorData(data)

      # Write the sensor data and the test result to USB stick, the UI,
      # and also to the shop floor.
      self._WriteSensorDataToFile(log_to_file, sn, test_pass, data)
      self.ui.CallJSFunction('displayDebugData', json.dumps(data))
      self.log('touchscreen_calibration',
               sn=sn, test_pass=test_pass, sensor_data=str(data))

      result = 'pass' if test_pass else 'fail'
      log_name = '%s_%s_%s_%s' % (self.start_time, sn, 'deltas', result)
      self._UploadLog(log_name, str(data))

      self.DriveProbeUp()

      if not self.sysfs.WriteSysfsSection('PostRead'):
        factory.console.error('Failed to write PostRead section to sys fs.')

      self.ui.CallJSFunction('showMessage',
                             'OK 测试完成' if test_pass else 'NO GOOD 测试失败')

      self.ui.Pass()

    except Exception as e:
      if not self.fixture:
        self._AlertFixtureDisconnected()
      raise e

  def _ConnectTouchDevice(self):
    """Make sure that the touch device is connected to the machine and
    the touch kernel module is inserted properly.
    """
    if not self.sysfs.CheckStatus():
      # The kernel module is inserted, but the touch device is not connected.
      self.sysfs.kernel_module.Remove()
      msg = ('Fail to detect the touchscreen.\n'
             'Insert the traveler board, and restart the test.\n'
             '无法侦测到面板。\n'
             '请移除小板後再重新插入小板，并重跑测试')
      self.ui.CallJSFunction('showMessage', msg)
      return False
    return True

  def _InsertAndDetectTouchKernelModule(self):
    """Insert the touch kernel module and make sure it is detected."""
    if (not self.sysfs.kernel_module.Insert() or
        not self.sysfs.kernel_module.IsDeviceDetected()):
      self.sysfs.kernel_module.Remove()
      factory.console.error('Failed to insert the kernel module: %s.',
                            self.sysfs.kernel_module.name)
      msg = ('Fail to detect the touchscreen.\n'
             'Remove and re-insert the traveler board. And restart the test.\n'
             '无法侦测到面板。\n'
             '请移除小板後再重新插入小板，并重跑测试')
      self.ui.CallJSFunction('showMessage', msg)
      return False
    return True

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

    self._calibration_thread = threading.Thread(target=self._Calibrate,
                                                args=[sn])
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
        self._monitor_thread = utils.StartDaemonThread(
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

    os.environ['DISPLAY'] = ':0'
    self.start_time = time.strftime('%Y%m%d.%H%M%S')

    self.dev_path = dev_path
    self.dump_frames = dump_frames
    self._CheckMountedMedia()

    self._RegisterEvents([
        # Events that are emitted from buttons on the factory UI.
        'ReadTest', 'RefreshFixture', 'RefreshTouchscreen', 'ProbeSelfTest',
        'DriveProbeDown', 'DriveProbeUp', 'ShutDown', 'QueryFixtureState',
        'RefreshNetwork',

        # Events that are emitted from other callback functions.
        'StartCalibration',
    ])

    self.ui.Run()
