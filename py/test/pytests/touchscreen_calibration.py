# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import subprocess
import threading
import time
import unittest
import StringIO

from collections import namedtuple

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
    self.sysfs_entry = '/sys/bus/i2c/devices/2-004a/object'

  def PreRead(self):
    """Initialize some data before reading the raw sensor data.

    The data here are highly platform dependent. The data here are for Link's
    touchscreen. May need to tune them for distinct platforms.
    """
    # Disable passing touch event to upper layer. This is to prevent
    # undesired action happen on UI when moving or touching the panel
    # under test.
    self.WriteSysfs('09000081')

    # Baseline the sensors before lowering the test probes.
    self.WriteSysfs('06000201')

  def PostRead(self):
    """Clean up after reading the raw sensor data.

    The data here are highly platform dependent. The data here are for Link's
    touchscreen. May need to tune them for distinct platforms.
    """
    # To indicate units are from DVT build, so config updater chooses
    # the correct raw file.
    self.WriteSysfs('26000002')

    # Correct the possibly corrupted 'report interval' value in FW config.
    self.WriteSysfs('070000FF')
    self.WriteSysfs('070001FF')

    # Let firmware backup settings to NV storage.
    self.WriteSysfs('06000155')

  def CheckStatus(self):
    """Checks if the touchscreen sysfs object is present.

    Returns:
      True if sysfs_entry exists
    """
    return os.path.exists(self.sysfs_entry)

  def WriteSysfs(self, to_write):
    """Writes to sysfs.

    Args:
      to_write: the contents to be written to sysfs
    """
    with open(self.sysfs_entry, 'w') as f:
      f.write(to_write)
    time.sleep(0.1)

  def Read(self, delta=False):
    """Reads 32 * 52 touchscreen sensors raw data.

    Args:
      delta: indicating whether to read deltas or refs.

    Returns:
      the list of raw sensor values
    """
    debugfs = ('/sys/kernel/debug/atmel_mxt_ts/2-004a/%s' %
               ('deltas' if delta else 'refs'))
    out_data = []
    with open(debugfs) as f:
      # The debug fs content is composed by 32 lines, and each
      # line contains 104 byte of 52 consecutive sensor values.
      for _ in range(32):
        line = f.read(104)
        data = []
        for i in range(52):
          # Correct endianness
          s = line[i * 2 + 1] + line[i * 2]
          val = int(s.encode('hex'), 16)
          # Correct signed values
          if val > 32768:
            val = val - 65535
          data.append(val)
        out_data.append(data)
    return out_data


class FixtureException(Exception):
  """A dummy exception class for FixutreSerialDevice."""
  pass


class FixutreSerialDevice(SerialDevice):
  """A serial device to control touchscreen fixture."""

  def __init__(self, timeout=10):
    super(FixutreSerialDevice, self).__init__()
    self.Connect(port=FindTtyByDriver(ARDUINO_DRIVER), timeout=timeout)

    factory.console.info('Sleep 2 seconds for arduino initialization.')
    time.sleep(2)
    self.AssertState([STATE.INIT, STATE.STOP_UP, STATE.EMERGENCY_STOP])

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

  def AssertState(self, expected_states):
    """Confirms that the arduino is in the specified state."""
    if not isinstance(expected_states, list):
      expected_states = [expected_states]
    actual_state = self.QueryState()
    if actual_state not in expected_states:
      msg = 'AssertState failed: actual state: "%s", expected_states: "%s".'
      raise FixtureException(msg % (actual_state, str(expected_states)))

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

  def ReadTest(self, dummy_event):
    """Reads the raw sensor data.."""
    if self.reader:
      data = self.reader.Read(delta=True)
      factory.console.info('Get data %s' % data)
      data = json.dumps(data)
      self.ui.CallJSFunction('displayDebugData', data)
    else:
      factory.console.info('No reader found')

  def ProbeSelfTest(self, dummy_event):
    """Execute the probe self test to confirm the fixture works properly."""
    self._CheckFixtureStateUp()
    self._DriveProbeDown()
    self._DriveProbeUp()

  def RefreshFixture(self, dummy_event):
    """Refreshes the fixture."""
    try:
      self.fixture = FixutreSerialDevice(timeout=10)
      if not self.fixture:
        raise FixtureException('Fail to create the fixture serial device.')
    except Exception as e:
      factory.console.info('Refresh fixture serial device exception, %s' % e)
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

  def RefreshTouchscreen(self, dummy_event):
    """Refreshes all possible saved state for the old touchscreen.

    This functions is called whenever an old touchscreen panel
    removed and a new one attached and awaiting for testing.
    After old states of previous touchscreen panel are cleared and
    new panel detected, show the sign on UI.
    """
    os.system('rmmod atmel_mxt_ts')
    os.system('modprobe atmel_mxt_ts')
    CONF_UPDATE_SCRIPT = ('/opt/google/touch/scripts/'
                          'chromeos-touch-config-update.sh')

    # Update touch-config
    with open(_TMP_STDOUT, 'w') as fd:
      subprocess.call(CONF_UPDATE_SCRIPT, stdout=fd)

    try:
      if self.reader.CheckStatus():
        factory.console.info('touchscreen exist')
        self.ui.CallJSFunction('setTouchscreenStatus', True)
        return
    except Exception as e:
      factory.console.info('Exception at refreshing touch screen: %s' % e)
    self.ui.CallJSFunction('setTouchscreenStatus', False)

  def _DriveProbeDown(self):
    """A wrapper to drive the probe down."""
    try:
      self.fixture.DriveProbeDown()
    except Exception as e:
      self.ui.CallJSFunction('showMessage',
                             'Probe not in the DOWN position, aborted\n'
                             '治具未就下位, 舍弃')
      raise e

  def _DriveProbeUp(self):
    """A wrapper to drive the probe up."""
    try:
      self.fixture.DriveProbeUp()
    except Exception as e:
      self.ui.CallJSFunction('showMessage',
                             'Probe not in the UP position, aborted\n'
                             '治具未就上位, 舍弃')
      raise e

  def _DumpOneFrameToLog(self, logger):
    """Dumps one frame to log.

    Args:
      logger: the log object
    """
    data = self.reader.Read(delta=True)
    logger.write('Dump one frame:\n')
    for row in data:
      logger.write(' '.join([str(val) for val in row]))
      logger.write('\n')

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

  def _VerifySensorData(self, data):
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
        self._DumpOneFrameToLog(log_to_file)
        time.sleep(0.1)

      self._DriveProbeDown()

      data = self.reader.Read(delta=True)
      factory.console.info('Get data %s' % data)

      # Verifies whether the sensor data is good or not.
      test_pass = self._VerifySensorData(data)

      # Write the sensor data and the test result to a file and on the UI.
      self._WriteSensorDataToFile(log_to_file, sn, test_pass, data)
      self.ui.CallJSFunction('displayDebugData', json.dumps(data))

      self._DriveProbeUp()

      self.reader.PostRead()

      self.ui.CallJSFunction('showMessage',
                             'OK 测试完成' if test_pass else 'NO GOOD 测试失败')

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

      # Events that are emitted from other callback functions.
      'StartCalibration',
    ])

    self.ui.Run()
