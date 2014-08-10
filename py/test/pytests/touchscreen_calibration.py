# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ConfigParser
import json
import os
import re
import StringIO
import threading
import time
import unittest

from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.fixture.touchscreen_calibration.fixture import (
    FixtureException, FixutreNativeUSB, FixutreSerialDevice)
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


class DebugDataReader():
  """Communicates with the touchscreen on system."""
  SYSFS_CONFIG = 'sysfs.conf'

  def __init__(self):
    self.num_rows = 41
    self.num_cols = 72
    self.DELTA_LOWER_BOUND = None
    self.DELTA_HIGHER_BOUND = None
    self.sysfs_entry = None
    self.debugfs = None
    self.config = self.GetSysfsConfig()
    self.GetConfigData()

  def GetSysfsConfig(self):
    """Get the sysfs config.

    The variables look as below:
    factory.CROS_FACTORY_LIB_PATH is "/usr/local/factory/py/test".
    static_dirname would be "touchscreen_calibration_static"
    """
    static_dirname = '_'.join([test_name, 'static'])
    config_filepath = os.path.join(factory.CROS_FACTORY_LIB_PATH,
                                   'pytests',
                                   static_dirname,
                                   self.SYSFS_CONFIG)
    config = ConfigParser.ConfigParser()
    try:
      with open(config_filepath) as f:
        config.readfp(f)
    except Exception:
      raise FixtureException('Failed to read sysfs config file: %s.' %
                             config_filepath)
    return config

  def GetConfigData(self):
    """Get sys fs paths and sensor parameters."""
    try:
      self.sysfs_entry = self.config.get('Sysfs', 'sysfs_entry')
      self.debugfs = self.config.get('Sysfs', 'debugfs')
    except Exception:
      raise FixtureException('Failed to get sys fs paths from conf file.')

    try:
      self.DELTA_LOWER_BOUND = self.config.get('TouchSensors',
                                               'DELTA_LOWER_BOUND')
      self.DELTA_HIGHER_BOUND = self.config.get('TouchSensors',
                                                'DELTA_HIGHER_BOUND')
    except Exception:
      raise FixtureException('Failed to get sensor parameters from conf file.')

  def WriteSysfsSection(self, section):
    """Write a section of values to sys fs."""
    factory.console.info('Write Sys fs section: %s', section)
    try:
      section_items = self.config.items(section)
      factory.console.info('Write Sys fs section: %s', section)
    except Exception:
      section_items = []
      factory.console.info('No items in Sys fs section: %s', section)

    for command, description in section_items:
      factory.console.info('  %s: %s', command, description)
      self.WriteSysfs(command)

  def CheckStatus(self):
    """Checks if the touchscreen sysfs object is present.

    Returns:
      True if sysfs_entry exists
    """
    return os.path.exists(self.sysfs_entry)

  def WriteSysfs(self, content):
    """Writes to sysfs.

    Args:
      content: the content to be written to sysfs
    """
    try:
      with open(self.sysfs_entry, 'w') as f:
        f.write(content)
    except Exception as e:
      factory.console.info('WriteSysfs failed to write %s: %s' % (content, e))
    time.sleep(0.1)

  def Read(self, delta=False):
    """Reads 32 * 52 touchscreen sensors raw data.

    Args:
      delta: indicating whether to read deltas or refs.

    Returns:
      the list of raw sensor values
    """
    debugfs = '%s/%s' % (self.debugfs, ('deltas' if delta else 'refs'))
    with open(debugfs) as f:
      # The debug fs content is composed of num_rows, where each row
      # contains (num_cols * 2) bytes of num_cols consecutive sensor values.
      num_bytes_per_row = self.num_cols * 2
      out_data = []
      for _ in range(self.num_rows):
        row_data = f.read(num_bytes_per_row)
        values = []
        for i in range(self.num_cols):
          # Correct endianness
          s = row_data[i * 2 + 1] + row_data[i * 2]
          val = int(s.encode('hex'), 16)
          # Correct signed value
          if val > 32768:
            val = val - 65535
          values.append(val)
        out_data.append(values)
    return out_data


class TouchscreenCalibration(unittest.TestCase):
  """Handles the calibration and controls the test fixture."""
  version = 1

  def setUp(self):
    """Sets up the object."""
    self._calibration_thread = None
    self.fixture = None
    self.dev_path = None
    self.dump_frames = 0
    self.reader = DebugDataReader()
    self.ui = UI()
    self._monitor_thread = None
    self.native_usb = None
    self.query_fixture_state_flag = False
    self._mounted_media_flag = True
    self._local_log_dir = '/var/tmp/%s' % test_name

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
    if self.reader:
      data = self.reader.Read(delta=True)
      factory.console.info('Get data %s' % data)
      data = json.dumps(data)
      self.ui.CallJSFunction('displayDebugData', data)
    else:
      factory.console.info('No reader found')

  def ProbeSelfTest(self, unused_event):
    """Execute the probe self test to confirm the fixture works properly."""
    self._CheckFixtureStateUp()
    self.DriveProbeDown()
    self.DriveProbeUp()

  def RefreshFixture(self, unused_event):
    """Refreshes the fixture."""
    try:
      self.fixture = FixutreSerialDevice()
      if not self.fixture:
        raise FixtureException('Fail to create the fixture serial device.')

    except Exception as e:
      factory.console.info('Refresh fixture serial device exception, %s' % e)
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
      if self.reader.CheckStatus():
        factory.console.info('touchscreen exist')
        self.ui.CallJSFunction('setTouchscreenStatus', True)
        return
    except Exception as e:
      factory.console.info('Exception at refreshing touch screen: %s' % e)
    self.ui.CallJSFunction('setTouchscreenStatus', False)

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
      factory.console.warn('%s: %s' % (fail_msg, e))

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

  def Mtplot(self, unused_event=None):
    """Shut down the host."""
    # The touchscreen device id string looks like
    #    Atmel maXTouch Touchscreen    id=13   [floating slave]
    xinput_device_id = self._CommandOutputSearch(
        'xinput list', 'touchscreen.+id=(\d+)\s+', re.I)
    if xinput_device_id is None:
      factory.console.warn('Cannot find xinput device id!')
      return

    # The device node looks like
    #    Device Node (250): "/dev/input/event6"
    cmd_str = 'xinput list-props %s' % xinput_device_id
    device_node = self._CommandOutputSearch(
        cmd_str, 'device node.*:\s*"(/dev/input/event\d+)"', re.I)
    if device_node is None:
      factory.console.warn('Cannot find device node!')
      return

    mtplot_cmd = 'mtplot %s' % device_node
    factory.console.info('Execute "%s"' % mtplot_cmd)
    self._ExecuteCommand(mtplot_cmd, fail_msg='Failed to launch mtplot.')

  def _DumpOneFrameToLog(self, logger, sn, frame_no):
    """Dumps one frame to log.

    Args:
      logger: the log object
    """
    data = self.reader.Read(delta=True)
    logger.write('Dump one frame:\n')
    for row in data:
      logger.write(' '.join([str(val) for val in row]))
      logger.write('\n')

    Log('touchscreen_calibration_before_touched_%d' % frame_no,
        sn=sn, sensor_data=str(data))

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
        if (value < self.reader.DELTA_LOWER_BOUND or
            value > self.reader.DELTA_HIGHER_BOUND):
          factory.console.info('  Failed at (row, col) (%d, %d) value %d' %
                               (row, col, value))
          test_pass = False

    return test_pass

  def _CheckSerialNumber(self, sn):
    """Check if the serial number is legitimate."""
    conf = self.reader.config
    if conf.has_section('Misc') and conf.has_option('Misc', 'sn_length'):
      sn_length = int(self.reader.config.get('Misc', 'sn_length'))
      if len(sn) != sn_length:
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
      factory.console.info('Start calibrating SN %s' % sn)
      log_to_file = StringIO.StringIO()

      self.reader.WriteSysfsSection('PreRead')

      # Dump whole frame a few times before probe touches panel.
      for f in range(self.dump_frames):           # pylint: disable=W0612
        factory.console.info('... dump_frames: %d', f)
        self._DumpOneFrameToLog(log_to_file, sn, f)
        time.sleep(0.1)

      self.DriveProbeDown()

      # Wait a while to let the probe touch the panel stably.
      time.sleep(1)

      data = self.reader.Read(delta=True)
      factory.console.info('Get data %s' % data)
      time.sleep(1)

      # Verifies whether the sensor data is good or not.
      test_pass = self._VerifySensorData(data)

      # Write the sensor data and the test result to USB stick, the UI,
      # and also to the shop floor.
      self._WriteSensorDataToFile(log_to_file, sn, test_pass, data)
      self.ui.CallJSFunction('displayDebugData', json.dumps(data))
      Log('touchscreen_calibration',
          sn=sn, test_pass=test_pass, sensor_data=str(data))

      self.DriveProbeUp()

      self.reader.WriteSysfsSection('PostRead')

      self.ui.CallJSFunction('showMessage',
                             'OK 测试完成' if test_pass else 'NO GOOD 测试失败')

      self.ui.Pass()

    except Exception as e:
      if not self.fixture:
        self._AlertFixtureDisconnected()
      raise e


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
      factory.console.info('Registered event %s' % event)
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
      factory.console.warn(msg % self._local_log_dir)
      self._MakeLocalLogDir()
      self._WriteLog('touchscreen_calibration_launch.txt',
                     '%s\n' % time.ctime())

  def QueryFixtureState(self, unused_event=None):
    """Query the fixture internal state including all sensor values."""
    try:
      self.native_usb.QueryFixtureState()
      self.query_fixture_state_flag = True
    except Exception as e:
      factory.console.warn('Failed to query fixture state: %s' % e)

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
          factory.console.info('      %s: %s' % (name, value))

  def _CreateMonitorPort(self):
    """Create a thread to monitor the native USB port."""
    self.native_usb = FixutreNativeUSB()

    if not self.native_usb:
      raise FixtureException('Fail to connect the native usb port.')

    try:
      self._monitor_thread = utils.StartDaemonThread(
          target=self._MonitorNativeUsb, args=[self.native_usb])
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

    self.dev_path = dev_path
    self.dump_frames = dump_frames
    self._CheckMountedMedia()

    self._RegisterEvents([
      # Events that are emitted from buttons on the factory UI.
      'ReadTest', 'RefreshFixture', 'RefreshTouchscreen', 'ProbeSelfTest',
      'DriveProbeDown', 'DriveProbeUp', 'ShutDown', 'QueryFixtureState',
      'Mtplot',

      # Events that are emitted from other callback functions.
      'StartCalibration',
    ])

    self.ui.Run()
