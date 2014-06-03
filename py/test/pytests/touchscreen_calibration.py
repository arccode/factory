# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import threading
import time
import unittest
import StringIO

from collections import namedtuple

from cros.factory.event_log import Log
from cros.factory.utils.serial_utils import FindTtyByDriver, SerialDevice
from cros.factory.test import factory
from cros.factory.test.media_util import MountedMedia
from cros.factory.test.test_ui import UI


# Temporary file to store stdout for commands executed in this test.
# Note that this file is to be examined only when needed, or just let it
# be overridden.
# Use shopfloor.UploadAuxLogs(_TMP_STDOUT) to upload this file to shopfloor
# server for future process and analyze when needed.
_TMP_STDOUT = '/tmp/stdout.txt'

ARDUINO_DRIVER = 'cdc_acm'


ArduinoCommand = namedtuple('ArduinoCommand', ['DOWN', 'UP', 'STATE', 'RESET'])
COMMAND = ArduinoCommand('d', 'u', 's', 'r')

ArduinoState = namedtuple('ArduinoState',
                          ['INIT', 'STOP_DOWN', 'STOP_UP', 'GOING_DOWN',
                           'GOING_UP', 'EMERGENCY_STOP'])
STATE = ArduinoState('i', 'D', 'U', 'd', 'u', 'e')


class DebugDataReader():
  """Communicates with the touchscreen on system."""
  def __init__(self):
    self.sysfs_entry = '/sys/bus/i2c/devices/9-004b/object'
    self.debugfs = '/sys/kernel/debug/atmel_mxt_ts/9-004b'
    self.num_rows = 41
    self.num_cols = 72

  def PreRead(self):
    """Initialize some data before reading the raw sensor data.

    The data here are highly platform dependent. The data here are for Link's
    touchscreen. May need to tune them for distinct platforms.
    """
    # Disable passing touch event to upper layer. This is to prevent
    # undesired action happen on UI when moving or touching the panel
    # under test.
    self.WriteSysfs('64000081')

    # YSIZE should be 72
    self.WriteSysfs('64001448')

    # Touch gain
    self.WriteSysfs('64001C14')

    # Baseline the sensors before lowering the test probes.
    self.WriteSysfs('06000201')

  def PostRead(self):
    """Clean up after reading the raw sensor data.

    The data here are highly platform dependent. The data here are for Link's
    touchscreen. May need to tune them for distinct platforms.
    """
    # Enable passing touch event to upper layer.
    self.WriteSysfs('64000083')

    # Adjust the following movement filters for touchscreen tests later.
    self.WriteSysfs('64002C80')
    self.WriteSysfs('64002F00')
    self.WriteSysfs('64003100')

    # The following line is to backup the settings in NV storage.
    self.WriteSysfs('06000155')

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


class FixtureException(Exception):
  """A dummy exception class for FixutreSerialDevice."""
  pass


class FixutreSerialDevice(SerialDevice):
  """A serial device to control touchscreen fixture."""

  def __init__(self, timeout=20):
    super(FixutreSerialDevice, self).__init__()
    self.Connect(port=FindTtyByDriver(ARDUINO_DRIVER), timeout=timeout)
    factory.console.info('Wait up to %d seconds for arduino initialization.' %
                         timeout)
    self.AssertStateWithTimeout([STATE.INIT, STATE.STOP_UP,
                                 STATE.EMERGENCY_STOP], timeout)

  def QueryState(self):
    """Queries the state of the arduino board."""
    try:
      state = self.SendReceive(COMMAND.STATE)
    except Exception:
      raise FixtureException('QueryState failed.')

    return state

  def IsStateUp(self):
    """Checks if the fixture is in the INIT or STOP_UP state."""
    return (self.QueryState() in [STATE.INIT, STATE.STOP_UP])

  def IsEmergencyStop(self):
    """Checks if the fixture is in the EMERGENCY_STOP state."""
    return (self.QueryState() == STATE.EMERGENCY_STOP)

  def AssertStateWithTimeout(self, expected_states, timeout):
    """Assert the state with timeout."""
    while True:
      result, state = self._AssertState(expected_states)
      if result is True:
        factory.console.info('state: %s (expected)', state)
        return
      factory.console.info('state: %s (transient, probe still moving)', state)
      time.sleep(1)
      timeout -= 1
      if timeout == 0:
        break

    msg = 'AssertState failed: actual state: "%s", expected_states: "%s".'
    raise FixtureException(msg % (state, str(expected_states)))

  def _AssertState(self, expected_states):
    """Confirms that the arduino is in the specified state.

    It returns True if the actual state is in the expected states;
    otherwise, it returns the actual state.
    """
    if not isinstance(expected_states, list):
      expected_states = [expected_states]
    actual_state = self.QueryState()
    return (actual_state in expected_states, actual_state)

  def AssertState(self, expected_states):
    result, _ = self._AssertState(expected_states)
    if result is not True:
      msg = 'AssertState failed: actual state: "%s", expected_states: "%s".'
      raise FixtureException(msg % (result, str(expected_states)))

  def DriveProbeDown(self):
    """Drives the probe to the 'down' position."""
    try:
      response = self.SendReceive(COMMAND.DOWN)
      factory.console.info('Send COMMAND.DOWN(%s). Receive state(%s).' %
                           (COMMAND.DOWN, response))
    except Exception:
      raise FixtureException('DriveProbeDown failed.')

    self.AssertState(STATE.STOP_DOWN)

  def DriveProbeUp(self):
    """Drives the probe to the 'up' position."""
    try:
      response = self.SendReceive(COMMAND.UP)
      factory.console.info('Send COMMAND.UP(%s). Receive state(%s).' %
                           (COMMAND.UP, response))
    except Exception:
      raise FixtureException('DriveProbeUp failed.')

    self.AssertState(STATE.STOP_UP)


class TouchscreenCalibration(unittest.TestCase):
  """Handles the calibration and controls the test fixture."""
  version = 1

  def setUp(self):
    """Sets up the object."""
    self._calibration_thread = None
    self.fixture = None
    self.dev_path = None
    self.dump_frames = None
    self.reader = DebugDataReader()
    self.ui = UI()

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

  def ShutDown(self, unused_event=None):
    """Shut down the host."""
    try:
      os.system('shutdown -H 0')
    except Exception as e:
      factory.console.info('Failed to shutdown the host: %s' % e)

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
    with MountedMedia(self.dev_path, 1) as mount_dir:
      with open(os.path.join(mount_dir, filename), 'a') as f:
        f.write(content)
    factory.console.info('Log wrote with filename[ %s ].' % filename)

  def _WriteSensorDataToFile(self, logger, sn, test_pass, data):
    """Writes the sensor data and the test result to a file."""
    logger.write('%s %s\n' % (sn, 'Pass' if test_pass else 'Fail'))
    for row in data:
      logger.write(' '.join([str(val) for val in row]))
      logger.write('\n')
    self._WriteLog(sn, logger.getvalue())

  def _VerifySensorDataOld(self, data):
    """Determines whether the sensor data is good or not."""
    # Sensor thresholds are determined by eyes usually from previous build data.
    DELTA_LOWER_BOUND = 300
    DELTA_HIGHER_BOUND = 1900

    test_pass = True
    row_num = 0
    for row in data:
      if row_num == 0:
        m = row[26]
        row_num = 1
      else:
        m = row[25]
        row_num = 0
      if (m < DELTA_LOWER_BOUND or m > DELTA_HIGHER_BOUND):
        factory.console.info('  Fail at row %s value %d' % (row, m))
        test_pass = False

    return test_pass

  def _VerifySensorData(self, data):
    """Determines whether the sensor data is good or not."""
    # Sensor thresholds are determined by eyes usually from previous build data.
    DELTA_LOWER_BOUND = 300
    DELTA_HIGHER_BOUND = 1900

    # There are 3 columns of metal fingers on the probe. The touched_cols are
    # derived through experiments. The values may vary from board to board.
    touched_cols = [1, 35, 69]
    test_pass = True
    for row, row_data in enumerate(data):
      for col in touched_cols:
        value = row_data[col]
        if (value < DELTA_LOWER_BOUND or value > DELTA_HIGHER_BOUND):
          factory.console.info('  Failed at (row, col) (%d, %d) value %d' %
                               (row, col, value))
          test_pass = False

    return test_pass

  def _Calibrate(self, sn):
    """The actual calibration method.

    Args:
      sn: the serial number of the touchscreen under test
    """
    self._CheckFixtureStateUp()

    try:
      factory.console.info('Start calibrating SN %s' % sn)
      log_to_file = StringIO.StringIO()

      self.reader.PreRead()

      # Dump whole frame a few times before probe touches panel.
      for f in range(self.dump_frames):           # pylint: disable=W0612
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

      self.reader.PostRead()

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

  def _CheckMountedMedia(self):
    """Checks the existence of the mounted media."""
    try:
      # Write the test launch time.
      self._WriteLog('touchscreen_calibration_launch.txt',
                     '%s\n' % time.ctime())
    except Exception:
      self.ui.CallJSFunction('showMessage',
                             'Insert a USB dongle to store the test results.\n'
                             'And then click 触控面板 on the left side of '
                             'the screen to restart the test.\n\n'
                             '请插入USB硬碟以储存测试结果\n'
                             '完成後，点击左方触控面板连结以重跑测试')
      raise FixtureException('Mounted media does not exist.')

  def runTest(self, dev_path=None, dump_frames=10):
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
    self._CheckMountedMedia()

    self._RegisterEvents([
      # Events that are emitted from buttons on the factory UI.
      'ReadTest', 'RefreshFixture', 'RefreshTouchscreen', 'ProbeSelfTest',
      'DriveProbeDown', 'DriveProbeUp', 'ShutDown',

      # Events that are emitted from other callback functions.
      'StartCalibration',
    ])

    self.ui.Run()
