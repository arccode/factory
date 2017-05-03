# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ALS fixture test.

Hot keys:

- Press Enter or Space keys to start test
- Press ESC to leave the test.

Data methods:

- Simple: reads parameters from 'param_dict' argument, but skips saving
  test results.
- USB: reads parameter file from USB drive, and saves test results in USB drive
  in subfolders ordered by date.
- Shopfloor: reads param file from shopfloor, and saves test results in
  shopfloor aux_logs. This is recommended over USB when there is
  Shopfloor environment because USB drive is not reliable.

Test parameters:

- Please check als_fixture_static/als.params.sample

Control Chamber:

- If control_chamber is True, chamber_conn_params must also be set.
- If chamber_conn_params is set to the string 'default', the default parameter
  CHAMBER_CONN_PARAMS_DEFAULT is used. Otherwise chamber_conn_params should be
  specified as a dict.

Usage examples::

    # ALS (Ambient Light Sensor) test
    OperatorTest(
      id='ALSCalibration',
      pytest_name='als_fixture',
      dargs={
        'mock_mode': False,
        'control_chamber': True,
        'chamber_conn_params': 'default',
        'chamber_cmd': {
          'LUX1': [('LUX1_ON\\n', 'LUX1_READY')],
          'LUX2': [('LUX2_ON\\n', 'LUX2_READY')],
          'LUX3': [('LUX3_ON\\n', 'LUX3_READY')],
          'OFF': [('OFF\\n', 'OFF_READY')]
        },
        'data_method': 'Shopfloor',
        'param_pathname': 'als/als.params.FATP',
        'ALS_val_path':
            '/sys/bus/iio/devices/iio:device0/in_illuminance_input'})

"""


import ast
import numpy as np
import os
import Queue
import re
import string
import threading
import time
import traceback
import unittest
from collections import namedtuple
from collections import OrderedDict

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.fixture.camera import als_light_chamber
from cros.factory.test.fixture import fixture_connection
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test import i18n
from cros.factory.test import leds
from cros.factory.test import network
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test.utils import media_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


# Test stages in ALS test. Prefix them with 'als_' to help query in Minijack.
STAGE00_START = 'als_start'  # start test
STAGE10_SN = 'als_sn'  # check serial number
STAGE20_INIT = 'als_init'  # init camera and try to read one image
STAGE30_ALS_LIGHT1 = 'als_light1'
STAGE40_ALS_LIGHT2 = 'als_light2'
STAGE50_ALS_LIGHT3 = 'als_light3'
STAGE60_ALS_CALCULATION = 'als_calculation'
STAGE70_VPD = 'als_vpd'
STAGE90_END = 'als_end'  # end test
STAGE100_SAVED = 'als_data_saved'  # test data saved


# CSS style classes defined in the corresponding HTML file.
STYLE_INFO = 'color_idle'
STYLE_PASS = 'color_good'
STYLE_FAIL = 'color_bad'


# HTML id.
ID_TEST_STATUS = 'test_status'
ID_MAIN_SCREEN_TITLE = 'main_screen_title'


# Text labels.
MSG_TITLE_ALS_TEST = i18n_test_ui.MakeI18nLabel('ALS Sensor Calibration')

# Test stage => message
MSG_TEST_STATUS = {
    STAGE00_START: _('Starting the test'),
    STAGE10_SN: _('Reading serial number'),
    STAGE20_INIT: _('Initializing camera'),
    STAGE30_ALS_LIGHT1: _('Reading Light1 ALS value'),
    STAGE40_ALS_LIGHT2: _('Reading Light2 ALS value'),
    STAGE50_ALS_LIGHT3: _('Reading Light3 ALS value'),
    STAGE60_ALS_CALCULATION: _('Calculate the ALS line'),
    STAGE70_VPD: _('Writing the ALS calibration data to vpd'),
    STAGE90_END: _('All tests are complete'),
    STAGE100_SAVED: _('Test data saved'),
}


# LED pattern.
LED_PATTERN = ((leds.LED_NUM | leds.LED_CAP, 0.05), (0, 0.05))


# Data structures.
DataMethod = type_utils.Enum(['SIMPLE', 'USB', 'SF'])
EventType = type_utils.Enum(['START_TEST', 'EXIT_TEST'])
TestStatus = type_utils.Enum(['PASSED', 'FAILED', 'UNTESTED', 'NA'])

InternalEvent = namedtuple('InternalEvent', 'event_type aux_data')


# Root failure causes (used for quick troubleshooting at factory).
FAIL_SN = 'SerialNumber'  # Missing camera or bad serial number.
FAIL_CHAMBER_ERROR = 'ChamberError'  # Fail to set light chamber chart
FAIL_ALS_NOT_FOUND = 'AlsNotFound'  # ALS not found.
FAIL_ALS_INIT = 'AlsInit'  # ALS initialization error.
FAIL_ALS_ORDER = 'AlsOrder'  # ALS order error.
FAIL_ALS_LIMIT = 'AlsLimit'  # ALS linear regression result not within limit.
FAIL_ALS_CALIB = 'AlsCalibration'  # ALS calibration error.
FAIL_ALS_VPD = 'AlsVPD'  # ALS write VPD error
FAIL_UNKNOWN = 'UnknownError'  # Unknown error.


# Event log keys.
EVENT_ALS_STATUS = 'camera_ALS_status'
EVENT_ALS_DATA = 'camera_ALS_data'


# Log output format.
LOG_FORMAT_ALS_SLOPE = 'ALS cal slope: %f'
LOG_FORMAT_ALS_INTERCEPT = 'ALS cal intercept: %f'


# Serial numbers.
SN_NA = 'NO_SN'
SN_INVALID = 'INVALID_SN'


# Chamber connection parameters
CHAMBER_CONN_PARAMS_DEFAULT = {
    'driver': 'pl2303',
    'serial_delay': 0,
    'serial_params': {
        'baudrate': 9600,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 1,
        'xonxoff': False,
        'rtscts': False,
        'timeout': None
    },
    'response_delay': 2
}


class _TestDelegate(object):
  """Delegate class for ALS (Ambient Light Sensor) test.

  We use four types of logging:

    1. factory console (factory.console.info())
    2. factory.log (self._Log())
    3. Save raw data to USB drive or shopfloor aux_logs folder (self._Log() and
       self._SaveTestData())
    4. Event log (event_log.Log())

  It has three public methods:
    - __init__()
    - LoadParamsAndShowTestScreen()
    - RunTest()

  Usage Example:

    delegate = _TestDelegate(...)
    delegate.LoadParamsAndShowTestScreen()
    while ...:  # loop test iterations
      delegate.RunTest()

  """

  def __init__(self, delegator, mock_mode, chamber,
               control_chamber, chamber_n_retries, chamber_retry_delay,
               data_method, local_ip, param_pathname, param_dict):
    """Initalizes _TestDelegate.

    Args:
      delegator: Instance of CameraFixture.
      mock_mode: Whether or not we are in mock mode.
      chamber: Instance of LightChamber.
      control_chamber: Whether or not to control the chart in the light chamber.
      chamber_n_retries: Number of retries when connecting.
      chamber_retry_delay: Delay between connection retries.
      data_method: DataMethod enum.
      local_ip: Check CameraFixture.ARGS for detailed description.
      param_pathname: ditto.
      param_dict: ditto.
    """

    self.delegator = delegator
    self.mock_mode = mock_mode
    self.chamber = chamber
    self.control_chamber = control_chamber
    self.chamber_n_retries = chamber_n_retries
    self.chamber_retry_delay = chamber_retry_delay

    # Basic config set by test_list.
    self.data_method = data_method
    self.local_ip = local_ip
    self.param_pathname = param_pathname

    # Internal context across multiple test iterations.
    if data_method == DataMethod.SIMPLE:
      self.params = param_dict
    else:
      self.params = None  # to be dynamically loaded later
    self.timing = {}  # test stage => completion ratio (0~1)

    self.usb_ready_event = None  # Internal flag is true if USB drive is ready.
    self.usb_dev_path = None

    # Internal context to be reset for each test iteration.
    # (Remember to reset them in _ResetForNewTest())
    self.logs = []  # list of log lines to be saved later.
    self.module_sn = SN_NA
    self.original_img = None
    self.analyzed_img = None

    # ALS test state
    self.light_index = -1

  def LoadParamsAndShowTestScreen(self):
    """Loads parameters and then shows main test screen."""
    # TODO(yllin): Move parameter loading to a standalone pytest and transform
    #              the parameters to JSON form.
    if self.data_method == DataMethod.USB:
      self.params = self._LoadParamsFromUSB()
    elif self.data_method == DataMethod.SF:
      self.params = self._LoadParamsFromShopfloor()

    media_utils.MediaMonitor('usb-serial', None).Start(
        on_insert=self._OnU2SInsertion, on_remove=self._OnU2SRemoval)

    # Basic pre-processing of the parameters.
    self._Log('Parameter version: %s\n' % self.params['version'])
    self._CalculateTiming()

    bind_keys = [test_ui.SPACE_KEY]
    if not self.params['ui']['ignore_enter_key']:
      bind_keys.append(test_ui.ENTER_KEY)
    for key in bind_keys:
      self.delegator.ui.BindKeyJS(
          key, 'if(event)event.preventDefault();\nOnButtonStartTestClick();')
    self.delegator.ui.CallJSFunction('ShowMainTestScreen',
                                     not self.params['sn']['auto_read'],
                                     self.params['sn']['format'])

  def _LoadParamsFromUSB(self):
    """Loads parameters from USB drive."""
    self.usb_ready_event = threading.Event()
    media_utils.RemovableDiskMonitor().Start(on_insert=self._OnUSBInsertion,
                                             on_remove=self._OnUSBRemoval)

    while self.usb_ready_event.wait():
      with media_utils.MountedMedia(self.usb_dev_path, 1) as mount_point:
        pathname = os.path.join(mount_point, self.param_pathname)
        try:
          with open(pathname, 'r') as f:
            return ast.literal_eval(f.read())
        except IOError as e:
          self._Log('Error: fail to read %r: %r' % (pathname, e))
      time.sleep(0.5)

  def _LoadParamsFromShopfloor(self):
    """Loads parameters from shopfloor."""
    network.PrepareNetwork(ip=self.local_ip, force_new_ip=False)

    factory.console.info('Reading %s from shopfloor', self.param_pathname)
    shopfloor_client = shopfloor.GetShopfloorConnection()
    return ast.literal_eval(
        shopfloor_client.GetParameter(self.param_pathname).data)

  def _CalculateTiming(self):
    """Calculates the timing of each test stage to self.timing."""
    chk_point = self.params['chk_point']
    cumsum = np.cumsum([d for _, d in chk_point])
    total_time = cumsum[-1]
    for i in xrange(len(chk_point)):
      if i > 0:
        self.timing[chk_point[i][0]] = cumsum[i - 1] / total_time
      else:
        self.timing[chk_point[i][0]] = 0

  def RunTest(self, input_sn):
    if self.delegator.args.assume_chamber_connected:
      self._SetupFixture()

    ret = self._ALSTest(input_sn)

    if self.delegator.args.auto_mode:
      self.delegator.PostInternalQueue(EventType.EXIT_TEST)

    return ret

  def _ALSTest(self, input_sn):
    self._ResetForNewTest()

    test_status = OrderedDict([
        (STAGE00_START, TestStatus.NA),
        (STAGE10_SN, TestStatus.UNTESTED),
        (STAGE20_INIT, TestStatus.UNTESTED),
        (STAGE30_ALS_LIGHT1, TestStatus.UNTESTED),
        (STAGE40_ALS_LIGHT2, TestStatus.UNTESTED),
        (STAGE50_ALS_LIGHT3, TestStatus.UNTESTED),
        (STAGE60_ALS_CALCULATION, TestStatus.UNTESTED),
        (STAGE70_VPD, TestStatus.UNTESTED),
        (STAGE90_END, TestStatus.UNTESTED),
        (STAGE100_SAVED, TestStatus.NA),
    ])

    intercept = None
    slope = None
    non_locals = {}  # hack to immitate nonlocal keyword in Python 3.x

    def update_progress(test_stage):
      non_locals['current_stage'] = test_stage
      self._UpdateTestProgress(test_stage)

    def update_status(success):
      if success:
        test_status[non_locals['current_stage']] = TestStatus.PASSED
      else:
        test_status[non_locals['current_stage']] = TestStatus.FAILED

    update_progress(STAGE00_START)
    update_status(True)

    # (1) Check / read module serial number.
    update_progress(STAGE10_SN)
    success = self._CheckSN(input_sn)
    update_status(success)
    if not success:
      return False, FAIL_SN

    conf = self.params['conf']

    # (2) Initializing ALS
    update_progress(STAGE20_INIT)
    success = self.chamber.EnableALS()
    update_status(success)
    if not success:
      return False, FAIL_ALS_NOT_FOUND

    LIGHT_STAGES = [STAGE30_ALS_LIGHT1, STAGE40_ALS_LIGHT2, STAGE50_ALS_LIGHT3]

    try:
      vals = []
      # (3) Measure light level at three different light levels
      while True:
        factory.console.info('try to switch light')
        # Go to the next lighting preset.
        if not self._SwitchToNextLight():
          break

        update_progress(LIGHT_STAGES[self.light_index])
        val = self.chamber.ReadMean(conf['read_delay'], conf['n_samples'])
        vals.append(val)
        self._Log('Lighting preset lux value: %d' %
                  conf['luxs'][self.light_index])
        self._Log('ALS value: %d' % val)

        # Check if it is a false read.
        if not val:
          update_status(False)
          self._Log('The ALS value is stuck at zero.')
          return False, FAIL_ALS_CALIB

        update_status(True)

      # (4) Check value ordering
      # Skipping value ordering check when in mock mode since we don't have
      # real ALS device
      if not self.mock_mode:
        for i, li in enumerate(conf['luxs']):
          for j in range(i):
            if ((li > conf['luxs'][j] and vals[j] >= vals[i]) or
                (li < conf['luxs'][j] and vals[j] <= vals[i])):
              self._Log('The ordering of ALS values is wrong.')
              return False, FAIL_ALS_ORDER

      # (5) Perform linear regression
      # The linear regression can be calculate as follows:
      # y = A + Bx
      # B = Covariance[x, y] / Variance[x]
      #     _    _
      # A = y - Bx
      #
      # Here our x is conf['luxs'] and y is vals

      def Mean(xs):
        return float(sum(xs)) / len(xs)

      def Variance(xs):
        return Mean([x * x for x in xs]) - Mean(xs) ** 2

      def Covariance(xs, ys):
        return Mean([x * y for x, y in zip(xs, ys)]) - Mean(xs) * Mean(ys)

      slope = Covariance(conf['luxs'], vals) / Variance(conf['luxs'])
      intercept = Mean(vals) - slope * Mean(conf['luxs'])

      # (6) Check if the result is within range
      update_progress(STAGE60_ALS_CALCULATION)
      if ((slope < conf['slope_limit'][0] or
           slope > conf['slope_limit'][1]) or
          intercept < conf['intercept_limit'][0] or
          intercept > conf['intercept_limit'][1]):
        update_status(False)
        self._Log('The result line spec is not within limit.')
        return False, FAIL_ALS_LIMIT
      update_status(True)

      # (7) Save ALS values to vpd for FATP test.
      update_progress(STAGE70_VPD)
      if (not self.mock_mode and
          self.delegator.dut.Call(conf['save_vpd'] % (slope, intercept))):
        update_status(False)
        self._Log('Writing VPD data failed!')
        return False, FAIL_ALS_VPD
      update_status(True)

      # (8) Final test result.
      update_progress(STAGE90_END)
      update_status(True)
    except fixture_connection.FixtureConnectionError:
      update_status(False)
      self._Log('The test fixture was disconnected!')
      return False, FAIL_CHAMBER_ERROR
    except Exception:
      update_status(False)
      self._Log('Failed to read values from ALS or unknown error.' +
                traceback.format_exc())
      return False, FAIL_UNKNOWN
    else:
      # (8) Logs to event log, and save to USB and shopfloor.
      update_progress(STAGE100_SAVED)
      self._UploadALSCalibData(
          test_status[STAGE90_END] == TestStatus.PASSED,
          {'sn': self.module_sn, 'vals': vals, 'slope': slope,
           'intercept': intercept})
      update_status(True)
      self._CollectALSLogs(test_status, slope, intercept)
      self._FlushEventLogs()

      # JavaScript needs to cleanup after the test is completed.
      self.delegator.ui.CallJSFunction('OnTestCompleted')

    return True, None

  def _SwitchToNextLight(self):
    self.light_index += 1
    if self.light_index >= len(self.params['conf']['luxs']):
      return False

    self.chamber.SetLight(self.params['conf']['light_seq'][self.light_index])
    time.sleep(self.params['conf']['light_delay'])
    return True

  def _ResetForNewTest(self):
    """Reset per-test context for new test."""
    self.logs = []
    self.module_sn = SN_NA
    self.light_index = -1

  def _UpdateTestProgress(self, test_stage):
    """Updates UI to show the test progress.

    Args:
      test_stage: Current test stage.
    """
    msg = MSG_TEST_STATUS[test_stage]
    self.delegator.ShowTestStatus(msg)
    self.delegator.ShowProgressBar(self.timing[test_stage])

  def _Log(self, text):
    """Custom log function to log to factory console and USB/shopfloor later."""
    factory.console.info(text)
    self.logs.append(text)

  def _UploadALSCalibData(self, test_passed, result):
    """Upload ALS calibration data to shopfloor.

    Args:
      test_passed: whether the IQ test has passed the criteria.
    """

    if test_passed:
      shopfloor_client = shopfloor.GetShopfloorConnection()
      shopfloor_client.SaveAuxLog(
          os.path.join('als', '%s.als' % self.module_sn),
          str(result))

  def _GetLogFilePrefix(self):
    return self.module_sn

  def _CheckSN(self, input_sn):
    """Checks and/or read module serial number.

    Args:
      input_sn: Serial number input on UI.
    """
    if self.params['sn']['auto_read']:
      success, input_sn = self._GetModuleSN()
    else:
      success = True

    if success:
      self.module_sn = input_sn
      self._Log('Serial number: %s' % self.module_sn)
      if not re.match(self.params['sn']['format'], self.module_sn):
        success = False
        self._Log('Error: invalid serial number.')

    return success

  def _GetModuleSN(self):
    """Read module serial number.

    The module serial number can be read from sysfs for USB camera or from
    i2c for MIPI camera or using a custom command.
    """

    if self.params['sn']['source'] == 'sysfs':
      return self._GetModuleSNSysfs()
    elif self.params['sn']['source'] == 'i2c':
      return self._GetModuleSNI2C()
    elif self.params['sn']['source'] == 'command':
      return self._GetModuleSNCommand()
    else:
      raise RuntimeError('Invalid camera SN source.')

  def _GetModuleSNSysfs(self):
    success, input_sn = self._ReadSysfs(self.params['sn']['sysfs_path'])

    if success:
      self._Log('Serial number: %s' % input_sn)
      if not re.match(self.params['sn']['format'], input_sn):
        self._Log('Error: invalid serial number.')
        return False, None
    else:
      return False, None

    return True, input_sn

  def _GetModuleSNI2C(self):
    i2c_param = self.params['sn']['i2c_param']

    try:
      # Power on camera so we can read from I2C
      fd = os.open(i2c_param['dev_node'], os.O_RDWR)

      slave = self.delegator.dut.i2c.GetSlave(
          i2c_param['bus'], i2c_param['chip_addr'], 16)
      return True, slave.Read(i2c_param['data_addr'], i2c_param['length'])[::-1]
    finally:
      os.close(fd)

  def _GetModuleSNCommand(self):
    command = self.params['sn']['command']
    try:
      result = self.delegator.dut.CheckOutput(command).strip()
    except Exception:
      return False, None
    else:
      return True, result

  def _ReadSysfs(self, pathname):
    """Read single-line data from sysfs.

    Args:
      pathname: Pathname in sysfs.

    Returns:
      Tuple of (success, read data).
    """
    def _FilterNonPrintable(s):
      return ''.join(c for c in s if c in string.printable)

    try:
      read_data = _FilterNonPrintable(
          self.delegator.dut.ReadSpecialFile(pathname)).rstrip()

    except IOError as e:
      self._Log('Fail to read %r: %r' % (pathname, e))
      return False, None
    if read_data.find('\n') >= 0:
      self._Log('%r contains multi-line data: %r' % (pathname, read_data))
      return False, None
    return True, read_data

  def _CollectALSLogs(self, test_status, slope, intercept):
    # 1. Log overall test states.
    self._Log('Test status:\n%s' % self._FormatOrderedDict(test_status))
    event_log.Log(EVENT_ALS_STATUS, **test_status)

    # 2. Log IQ data.
    ALS_data = {}

    def mylog(value, key, log_text_fmt):
      self._Log((log_text_fmt % value))
      ALS_data[key] = value

    ALS_data['module_sn'] = self.module_sn
    mylog(slope, 'als_cal_slope', LOG_FORMAT_ALS_SLOPE)
    mylog(intercept, 'als_cal_intercept', LOG_FORMAT_ALS_INTERCEPT)

    event_log.Log(EVENT_ALS_DATA, **ALS_data)

  def _FlushEventLogs(self):
    if self.data_method == DataMethod.SF:
      goofy = state.get_instance()
      goofy.FlushEventLogs()

  def _FormatOrderedDict(self, ordered_dict):
    l = ['{']
    l += ["  '%s': %s," % (key, ordered_dict[key]) for key in ordered_dict]
    l.append('}')
    return '\n'.join(l)

  def _SetupFixture(self):
    """Initialize the communication with the fixture."""
    try:
      self.chamber.Connect()
    except Exception as e:
      self._Log(str(e))
      self._Log('Failed to initialize the test fixture.')
      return False
    self._Log('Test fixture successfully initialized.')
    return True

  def _OnUSBInsertion(self, dev_path):
    self.usb_dev_path = dev_path
    self.usb_ready_event.set()
    self.delegator.ui.CallJSFunction('UpdateUSBStatus', True)

  def _OnUSBRemoval(self, dev_path):
    del dev_path  # Unused.
    self.usb_ready_event.clear()
    self.usb_dev_path = None
    self.delegator.ui.CallJSFunction('UpdateUSBStatus', False)

  def _OnU2SInsertion(self, _):
    if self.params:
      cnt = 0
      while not self._SetupFixture():
        cnt += 1
        if cnt >= self.chamber_n_retries:
          self.delegator.ui.CallJSFunction('UpdateFixtureStatus', False)
          return
        time.sleep(self.chamber_retry_delay)
      self.delegator.ui.CallJSFunction('UpdateFixtureStatus', True)

  def _OnU2SRemoval(self, _):
    if self.params:
      self.delegator.ui.CallJSFunction('UpdateFixtureStatus', False)


class ALSFixture(unittest.TestCase):
  """ALS fixture main class."""
  ARGS = [
      # Some options
      Arg('auto_mode', bool, 'Automatically start and end the test.',
          default=False),

      # chamber connection
      Arg('control_chamber', bool, 'Whether or not to control the chart in the '
          'light chamber.', default=False),
      Arg('assume_chamber_connected', bool, 'Assume chamber is connected on '
          'test startup. This is useful when running fixture-based testing. '
          "The OP won't have to reconnect the fixture everytime.",
          default=False),
      Arg('chamber_conn_params', (dict, str), 'Chamber connection parameters, '
          "either a dict or 'default'", default=None, optional=True),
      Arg('chamber_cmd', dict, 'A mapping between charts listed in '
          'LightChamber.Charts and a list of tuple (cmd, response) required to '
          "activate the chart. 'response' can be None to disable checking.",
          default=None, optional=True),
      Arg('chamber_n_retries', int, 'Number of retries when connecting.',
          default=10),
      Arg('chamber_retry_delay', int, 'Delay between connection retries.',
          default=2),

      # test environment
      Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
          default=False),
      Arg('data_method', str, 'How to read parameters and save test results. '
          'Supported types: Simple, Shopfloor, and USB.', default='USB'),
      Arg('param_pathname', str, 'Pathname of parameter file on '
          'USB drive or shopfloor.', default='camera.params'),
      Arg('local_ip', str, 'Local IP address for connecting shopfloor. '
          'when data_method = Shopfloor. Set as None to use DHCP.',
          default=None, optional=True),
      Arg('param_dict', dict, 'The parameters dictionary. '
          'when data_method = Simple.',
          default=None, optional=True),
      Arg('ALS_val_path', str, 'ALS value path', default=None, optional=True),

  ]

  # self.args.data_method => DataMethod
  DATA_METHODS = {
      'Simple': DataMethod.SIMPLE,
      'USB': DataMethod.USB,
      'Shopfloor': DataMethod.SF
  }

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.internal_queue = Queue.Queue()

    # pylint: disable=no-member
    os.chdir(os.path.join(os.path.dirname(__file__), '%s_static' %
                          self.test_info.pytest_name))

    assert (self.args.data_method != 'Simple' or
            self.args.param_dict is not None)

    if self.args.chamber_conn_params == 'default':
      chamber_conn_params = CHAMBER_CONN_PARAMS_DEFAULT
    else:
      chamber_conn_params = self.args.chamber_conn_params

    fixture_conn = None
    if self.args.control_chamber:
      if self.args.mock_mode:
        script = dict([(k.strip(), v.strip()) for k, v in
                       reduce(lambda a, b: a + b,
                              self.args.chamber_cmd.values(), [])])
        fixture_conn = fixture_connection.MockFixtureConnection(script)
      else:
        fixture_conn = fixture_connection.SerialFixtureConnection(
            **chamber_conn_params)

    self.chamber = als_light_chamber.ALSLightChamber(
        dut=self.dut,
        val_path=self.args.ALS_val_path,
        scale_path=None,
        fixture_conn=fixture_conn,
        fixture_cmd=self.args.chamber_cmd,
        mock_mode=self.args.mock_mode)

    self.ui = test_ui.UI()
    self.ui.AddEventHandler(
        'start_test_button_clicked',
        lambda js_args: self.PostInternalQueue(EventType.START_TEST, js_args))
    self.ui.AddEventHandler(
        'exit_test_button_clicked',
        lambda _: self.PostInternalQueue(EventType.EXIT_TEST))
    self.ui.BindKey(
        test_ui.ESCAPE_KEY,
        lambda _: self.PostInternalQueue(EventType.EXIT_TEST))

  def runTest(self):
    self.ui.RunInBackgroud(self._RunDeligateTest)
    self.ui.Run()

  def _RunDeligateTest(self):
    """Main routine for ALS test."""
    delegate = _TestDelegate(
        delegator=self,
        mock_mode=self.args.mock_mode,
        chamber=self.chamber,
        control_chamber=self.args.control_chamber,
        chamber_n_retries=self.args.chamber_n_retries,
        chamber_retry_delay=self.args.chamber_retry_delay,
        data_method=self.DATA_METHODS[self.args.data_method],
        local_ip=self.args.local_ip,
        param_pathname=self.args.param_pathname,
        param_dict=self.args.param_dict)

    self.ui.CallJSFunction('InitForTest', self.args.data_method,
                           self.args.control_chamber)

    self.ui.CallJSFunction('UpdateTextLabel', MSG_TITLE_ALS_TEST,
                           ID_MAIN_SCREEN_TITLE)

    delegate.LoadParamsAndShowTestScreen()

    if self.args.assume_chamber_connected:
      self.ui.CallJSFunction('UpdateFixtureStatus', True)

    if self.args.auto_mode and delegate.params['sn']['auto_read']:
      self.PostInternalQueue(EventType.START_TEST)

    # Loop to repeat the test until user chooses 'Exit Test'.  For module-level
    # testing, it may test thousands of DUTs without leaving the test. The test
    # passes or fails depending on the last test result.
    success, fail_cause = False, None
    while True:
      event = self.PopInternalQueue(wait=True)
      if event.event_type == EventType.START_TEST:
        with leds.Blinker(LED_PATTERN):
          input_sn = ''
          if event.aux_data is not None:
            input_sn = event.aux_data.data.get('input_sn', '')

          # pylint: disable=unpacking-non-sequence
          success, fail_cause = delegate.RunTest(input_sn)

        if success:
          self.ShowTestStatus(i18n.NoTranslation('ALS: PASS'), style=STYLE_PASS)
        else:
          self.ShowTestStatus(i18n.NoTranslation('ALS: FAIL %r' % fail_cause),
                              style=STYLE_FAIL)
      elif event.event_type == EventType.EXIT_TEST:
        if success:
          self.ui.Pass()
        else:
          self.fail('Test ALS failed - fail cause = %r.' % fail_cause)
        break
      else:
        raise ValueError('Invalid event type.')

  def PostInternalQueue(self, event_type, aux_data=None):
    """Posts an event to internal queue.

    Args:
      event_type: EventType.
      aux_data: Extra data.
    """
    self.internal_queue.put(InternalEvent(event_type, aux_data))

  def PopInternalQueue(self, wait):
    """Pops an event from internal queue.

    Args:
      wait: A bool flag to wait forever until internal queue has something.

    Returns:
      The first InternalEvent in internal queue. None if 'wait' is False and
      internal queue is empty.
    """
    if wait:
      return self.internal_queue.get(block=True, timeout=None)
    else:
      try:
        return self.internal_queue.get_nowait()
      except Queue.Empty:
        return None

  def ShowTestStatus(self, msg, style=STYLE_INFO):
    """Shows test status.

    Args:
      msg: i18n text.
      style: CSS style.
    """
    label = i18n_test_ui.MakeI18nLabelWithClass(msg, style)
    self.ui.CallJSFunction('UpdateTextLabel', label, ID_TEST_STATUS)

  def ShowProgressBar(self, completion_ratio):
    """Update the progress bar.

    Args:
      completion_ratio: Completion ratio.
    """
    percent = int(round(completion_ratio * 100))
    self.ui.CallJSFunction('UpdateProgressBar', '%d%%' % percent)
