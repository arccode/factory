# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Calibration test for light sensor (a chamber is needed).

Hot keys:

- Press Enter or Space keys to start test
- Press ESC to leave the test.

Test configs:

- Please check light_sensor_calibration.json and
  light_sensor_calibration.schema.json

Control Chamber:

- If control_chamber is True, chamber_conn_params must also be set.
- If chamber_conn_params is set to the string 'default', the default parameter
  CHAMBER_CONN_PARAMS_DEFAULT is used. Otherwise chamber_conn_params should be
  specified as a dict.

Usage examples::

    {
      "pytest_name": "light_sensor_calibration",
      "args": {
        "chamber_conn_params": "default",
        "chamber_cmd": {
          "OFF": [
            ["OFF\\n", "OFF_READY"]
          ],
          "LUX1": [
            ["LUX1_ON\\n", "LUX1_READY"]
          ],
          "LUX3": [
            ["LUX3_ON\\n", "LUX3_READY"]
          ],
          "LUX2": [
            ["LUX2_ON\\n", "LUX2_READY"]
          ]
        },
        "mock_mode": false,
        "control_chamber": true
      }
    }

"""


from collections import namedtuple
import json
import logging
import numpy as np
import os
import Queue
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import ambient_light_sensor
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.fixture import fixture_connection
from cros.factory.test.fixture.light_sensor import light_chamber
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import device_data
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import kbd_leds
from cros.factory.test.utils import media_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


# CSS style classes defined in the corresponding HTML file.
STYLE_INFO = 'color_idle'
STYLE_PASS = 'color_good'
STYLE_FAIL = 'color_bad'

# HTML id.
ID_FIXTURE_STATUS = 'fixture_status'
ID_TEST_STATUS = 'test_status'

STATE_HTML = """
  <div style="font-size: 250%%">
    <div id='%s'></div>
    <div id='%s'></div>
  </div>
""" % (ID_FIXTURE_STATUS, ID_TEST_STATUS)

CSS = """
  .%s {
  color: black;
}
  .%s {
  color: #7db72f;
}
  .%s {
  color: #c9151b;
}
""" % (STYLE_INFO, STYLE_PASS, STYLE_FAIL)

# Text labels.
MSG_TITLE_ALS_TEST = i18n_test_ui.MakeI18nLabel('ALS Sensor Calibration')
MSG_FIXTURE_CONNNECTED = i18n_test_ui.MakeI18nLabelWithClass(
    'Fixture Connected', STYLE_PASS)
MSG_FIXTURE_DISCONNECTED = i18n_test_ui.MakeI18nLabelWithClass(
    'Fixture Disconnected', STYLE_FAIL)

# LED pattern.
LED_PATTERN = ((kbd_leds.LED_NUM | kbd_leds.LED_CAP, 0.05), (0, 0.05))

# Data structures.
EventType = type_utils.Enum(['START_TEST', 'EXIT_TEST'])
FIXTURE_STATUS = type_utils.Enum(['CONNECTED', 'DISCONNECTED'])


InternalEvent = namedtuple('InternalEvent', 'event_type aux_data')

FAIL_CONFIG = 'ConfigError'  # Config file error.
FAIL_SN = 'SerialNumber'  # Missing camera or bad serial number.
FAIL_CHAMBER_ERROR = 'ChamberError'  # Chamber connection error.
FAIL_ALS_NOT_FOUND = 'AlsNotFound'  # ALS not found.
FAIL_ALS_CLEAN = 'AlsClean'  # ALS coefficient clean up error.
FAIL_ALS_SAMPLE = 'AlsSample'  # ALS sampling error.
FAIL_ALS_ORDER = 'AlsOrder'  # ALS order error.
FAIL_ALS_CALIB = 'AlsCalibration'  # ALS calibration error.
FAIL_ALS_CALC = 'AlsCalculation'  # ALS coefficient calculation error.
FAIL_ALS_VALID = 'AlsValidating'  # ALS validating error.
FAIL_ALS_VPD = 'AlsVPD'  # ALS write VPD error
FAIL_ALS_CONTROLLER = 'ALSController'  # ALS controller error.
FAIL_UNKNOWN = 'UnknownError'  # Unknown error

# ALS mock mode.
ALS_MOCK_VALUE = 10

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


class ALSFixture(unittest.TestCase):
  """ALS fixture main class."""
  ARGS = [
      # chamber connection
      Arg('control_chamber', bool, 'Whether or not to control the chart in the '
          'light chamber.', default=False),
      Arg('assume_chamber_connected', bool, 'Assume chamber is connected on '
          'test startup. This is useful when running fixture-based testing. '
          "The OP won't have to reconnect the fixture everytime.",
          default=True),
      Arg('chamber_conn_params', (dict, str), 'Chamber connection parameters, '
          "either a dict, defaults to None", default=None, optional=True),
      Arg('chamber_cmd', dict, 'A dict for name of lightning to a '
          '(cmd, cmd_response) tuple.', default=None, optional=False),
      Arg('chamber_n_retries', int, 'Number of retries when connecting.',
          default=10),
      Arg('chamber_retry_delay', int, 'Delay between connection retries.',
          default=2),

      # test environment
      Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
          default=False),
      Arg('config_dict', dict, 'The config dictionary. '
          'If None, then the config is loaded by config_utils.LoadConfig().',
          default=None, optional=True),

  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.internal_queue = Queue.Queue()

    try:
      self.als_controller = self.dut.ambient_light_sensor.GetController()
    except Exception as e:
      self._LogFailure(FAIL_ALS_NOT_FOUND,
                       'Error getting ALS controller: %s' % e.message)
      raise e

    # Loads config.
    try:
      self.config = self.args.config_dict or config_utils.LoadConfig()
      if self.config is None:
        raise ValueError('No available configuration.')
      self._LogConfig()
    except Exception as e:
      logging.exception('Error logging config file: %s', e.message)
      raise e

    self.read_delay = self.config['read_delay']
    self.n_samples = self.config['n_samples']

    try:
      if self.args.chamber_conn_params is None:
        chamber_conn_params = CHAMBER_CONN_PARAMS_DEFAULT
      else:
        chamber_conn_params = self.args.chamber_conn_params

      self.fixture_conn = None
      if self.args.control_chamber:
        if self.args.mock_mode:
          script = dict(
              [(k.strip(), v.strip())
               for k, v in sum(self.args.chamber_cmd.values(), [])])
          self.fixture_conn = fixture_connection.MockFixtureConnection(script)
        else:
          self.fixture_conn = fixture_connection.SerialFixtureConnection(
              **chamber_conn_params)

      self.chamber = light_chamber.LightChamber(
          fixture_conn=self.fixture_conn, fixture_cmd=self.args.chamber_cmd)
    except Exception as e:
      self._LogFailure(FAIL_CHAMBER_ERROR,
                       'Error setting up ALS chamber: %s' % e.message)

    self.all_sampled_lux = []  # mean of sampled lux for each light
    self.scale_factor = None  # value of calibrated scale factor
    self.bias = None  # value of calibrated bias
    self.light_index = -1  # ALS test stage
    self.dummy_index = 0  # Dummy index key for Series with only one log

    self.ui = test_ui.UI()
    self.ui.AppendCSS(CSS)
    self.template = ui_templates.OneSection(self.ui)
    self.template.SetTitle(MSG_TITLE_ALS_TEST)
    self.template.SetState(STATE_HTML)

    self.ui.BindKey(
        test_ui.ESCAPE_KEY,
        lambda _: self._PostInternalQueue(EventType.EXIT_TEST))

  def _Log(self, text):
    """Custom log function to log."""
    logging.info(text)
    factory.console.info(text)

  def _LogSerialNumber(self):
    testlog.AddArgument(device_data.KEY_SERIALS,
                        device_data.GetAllSerialNumbers())

  def _LogArgument(self, key, value, description):
    testlog.AddArgument(key, value, description)
    self._Log("%s=%s" % (key, value))

  def _LogConfig(self):
    with file_utils.UnopenedTemporaryFile() as config_file_path:
      with open(config_file_path, 'w') as config_file:
        json.dump(self.config, config_file)
      testlog.AttachFile(
          path=config_file_path,
          mime_type='application/json',
          name='light_sensor_calibration_config.json',
          description=os.path.basename(config_file_path),
          delete=False)

  def _LogFailure(self, code, details):
    testlog.AddFailure(code, details)
    message = 'FAIL %r: %r' % (code, details)
    logging.exception(message)
    factory.console.info(message)

  def _LogValue(self, srs, key, value, call_update=True, prefix=''):
    """Custom log function to log."""
    srs.LogValue(key=key, value=value, call_update=call_update)
    factory.console.info('%s%r: %r', prefix, key, value)

  def _CheckValue(self, srs, key, value, vmin, vmax, call_update=True):
    """Using testlog to check value is within the boundary"""
    success = srs.CheckValue(key, value, vmin, vmax, call_update)
    self._Log('%s %r: %r (min=%s, max=%s)' % (success, key, value, vmin, vmax))
    return success

  def _ALSTest(self):
    try:
      self._ShowTestStatus(_('Logging serial numbers'))
      self._LogSerialNumber()
    except Exception as e:
      self._LogFailure(FAIL_SN, 'Error logging serial numbers: %s' % e.message)
      raise e

    try:
      self._ShowTestStatus(_('Cleaning up calibration values'))
      if not self.args.mock_mode:
        self.als_controller.CleanUpCalibrationValues()
    except Exception as e:
      self._LogFailure(FAIL_ALS_CLEAN, 'Error cleaning up calibration values:'
                       ' %s' % e.message)
      raise e

    while True:
      try:
        if not self._SwitchToNextLight():
          break

        light_name = self.config['light_seq'][self.light_index]
        self._ShowTestStatus(
            i18n.StringFormat(_('Sampling {name}'), name=light_name))
        self._SampleALS(light_name)
      except Exception as e:
        self._LogFailure(FAIL_ALS_SAMPLE, 'Error sampling lighting %d %s: %s' %
                         (self.light_index, light_name, e.message))
        raise e

    try:
      self._ShowTestStatus(_('Checking ALS ordering'))
      self._CheckALSOrdering()
    except Exception as e:
      self._LogFailure(FAIL_ALS_ORDER,
                       'Error checking als ordering: %s' % e.message)
      raise e


    try:
      self._ShowTestStatus(_('Calculating calibration coefficients'))
      self._CalculateCalibCoef()
    except Exception as e:
      self._LogFailure(FAIL_ALS_CALC, 'Error calculating calibration'
                       ' coefficient: %s' % e.message)
      raise e

    try:
      self._ShowTestStatus(_('Saving calibration coefficients to VPD'))
      self._SaveCalibCoefToVPD()
    except Exception as e:
      self._LogFailure(FAIL_ALS_VPD, 'Error setting calibration'
                       ' coefficient to VPD: %s' % e.message)
      raise e

    try:
      self._ShowTestStatus(_('Validating ALS'))
      light_name = self.config['validating_light']
      self._SwitchLight(light_name)
      self._ValidateALS(light_name)
    except Exception as e:
      self._LogFailure(FAIL_ALS_VALID,
                       'Error validating calibrated ALS: %s' % e.message)
      raise e

  def _OnU2SInsertion(self, dev_path):
    del dev_path  # unused
    cnt = 0
    while cnt < self.args.chamber_n_retries:
      try:
        self._SetupFixture()
        self._SetFixtureStatus(FIXTURE_STATUS.CONNECTED)
        return
      except Exception:
        cnt += 1
        self._SetFixtureStatus(FIXTURE_STATUS.DISCONNECTED)
        time.sleep(self.args.chamber_retry_delay)
    raise light_chamber.LightChamberError('Error connecting to light chamber')

  def _OnU2SRemoval(self, dev_path):
    del dev_path  # unused
    self._SetFixtureStatus(FIXTURE_STATUS.DISCONNECTED)

  def _SetFixtureStatus(self, status):
    if status == FIXTURE_STATUS.CONNECTED:
      label = MSG_FIXTURE_CONNNECTED
    elif status == FIXTURE_STATUS.DISCONNECTED:
      label = MSG_FIXTURE_DISCONNECTED
    else:
      raise ValueError('Unknown fixture status %s', str(status))
    self.ui.SetHTML(label, id=ID_FIXTURE_STATUS)

  def _SetupFixture(self):
    """Initialize the communication with the fixture."""
    try:
      self.chamber.Connect()
    except Exception as e:
      self._LogFailure(FAIL_CHAMBER_ERROR, 'Error initializing the ALS fixture:'
                       ' %s' % e.message)
      raise e
    self._Log('Test fixture successfully initialized.')

  def _SwitchLight(self, light):
    self._Log("Switching to lighting %s." % light)
    self._ShowTestStatus(
        i18n.StringFormat(_('Switching to lighting {name}'), name=light))
    try:
      self.chamber.SetLight(light)
    except Exception as e:
      self._LogFailure(FAIL_CHAMBER_ERROR,
                       'Error commanding ALS chamber: %s' % e.message)
      raise e
    time.sleep(self.config['light_delay'])

  def _SwitchToNextLight(self):
    self.light_index += 1
    if self.light_index >= len(self.config['luxs']):
      return False
    self._SwitchLight(self.config['light_seq'][self.light_index])
    return True

  def _SampleLuxValue(self, series, delay, samples):
    if self.args.mock_mode:
      return ALS_MOCK_VALUE
    try:
      buf = []
      start_time = time.time()
      for unused_i in xrange(samples):
        time.sleep(delay)
        buf.append(self.als_controller.GetLuxValue())
        self._LogValue(series, time.time() - start_time, buf[-1])
    except ambient_light_sensor.AmbientLightSensorException as e:
      logging.exception('Error reading ALS value: %s', e.message)
      raise e
    return float(np.mean(buf))

  def _SampleALS(self, light_name):
    srs = testlog.CreateSeries(
        name='Calibrating' + light_name,
        description=('Sampled calibrating lux for %s over time' % light_name),
        key_unit='seconds',
        value_unit='lx')
    sampled_lux = self._SampleLuxValue(srs, self.read_delay, self.n_samples)
    preset_lux = self.config['luxs'][self.light_index]
    self._LogArgument('Preset%s' % light_name, preset_lux,
                      'Preset calibrating lux value.')
    self._LogArgument('Mean%s' % light_name, sampled_lux,
                      'Mean of sampled calibrating lux value.')
    self.all_sampled_lux.append(sampled_lux)

  def _ValidateALS(self, light_name):
    # Validating test result with presetted validating light:
    # y * (1 - validating_err_limit) <= x <=  y * (1 + validating_err_limit)
    # where y is light intensity v_lux, and x is read lux value v_val.
    srs = testlog.CreateSeries(
        name='ValidatingLux',
        description=('Sampled validating lux for %s over time' % light_name),
        key_unit='seconds',
        value_unit='lx')
    sampled_vlux = self._SampleLuxValue(srs, self.read_delay, self.n_samples)
    preset_vlux = float(self.config['validating_lux'])
    self._LogArgument('Preset%s' % light_name, preset_vlux,
                      'Preset validating lux value.')
    self._LogArgument('MeanValidatingLux', sampled_vlux,
                      'Mean of sampled validating lux value.')
    srs = testlog.CreateSeries(
        name='ValidatingLuxMean',
        description=('Mean of sampled validating lux for %s' % light_name),
        key_unit=None,
        value_unit='lx')
    err_limit = float(self.config['validating_err_limit'])
    lower_bound = preset_vlux * (1 - err_limit)
    upper_bound = preset_vlux * (1 + err_limit)
    result = self._CheckValue(
        srs,
        key=self.dummy_index,
        value=sampled_vlux,
        vmin=lower_bound,
        vmax=upper_bound)
    if not result and not self.args.mock_mode:
      raise ValueError('Error validating calibrated als, got %s out of'
                       ' range (%s, %s)', sampled_vlux, lower_bound,
                       upper_bound)

  def _CheckALSOrdering(self):
    if self.args.mock_mode:
      return
    luxs = self.config['luxs']
    for i, li in enumerate(luxs):
      for j in range(i):
        if ((li > luxs[j] and
             self.all_sampled_lux[j] >= self.all_sampled_lux[i]) or
            (li < luxs[j] and
             self.all_sampled_lux[j] <= self.all_sampled_lux[i])):
          raise ValueError('The ordering of ALS value is wrong.')

  def _CalculateCalibCoef(self):
    # Calculate bias and scale factor (sf).
    # Scale Factor sf = mean(Slope((x0,y0), (x1,y1)), ... ,
    #                        Slope((x0,y0), (xn,yn)))
    # bias = y0/sf - x0
    # Here our x is self.all_sampled_lux, y is self.config['luxs']
    if self.args.mock_mode:
      return

    def Slope(base, sample):
      return float((sample[1] - base[1]) / (sample[0] - base[0]))

    def ScaleFactor(xs, ys):
      base = (xs[0], ys[0])
      samples = zip(xs[1:], ys[1:])
      return float(np.mean([Slope(base, s) for s in samples]))

    self.scale_factor = ScaleFactor(self.all_sampled_lux,
                                    self.config['luxs'])
    self.bias = (
        self.config['luxs'][0] / self.scale_factor - self.all_sampled_lux[0])
    self._LogArgument(
        'CalibCoefficientScaleFactor',
        self.scale_factor,
        description='Calibrated coefficients scale factor.')
    self._LogArgument(
        'CalibCoefficientBias',
        self.bias,
        description='Calibrated coefficients bias.')

  def _SaveCalibCoefToVPD(self):
    if self.args.mock_mode:
      return

    self.dut.vpd.ro.Update({
        'als_cal_slope': str(self.scale_factor),
        'als_cal_intercept': str(self.bias)
    })

    if self.config['force_light_init']:
      # Force als adopts the calibrated vpd values.
      self.als_controller.ForceLightInit()
    else:
      # The light-init script doesn't act as expected, this is a workaround.
      self.als_controller.SetCalibrationIntercept(self.bias)
      self.als_controller.SetCalibrationSlope(self.scale_factor)

  def runTest(self):
    self.ui.RunInBackground(self._RunTest)
    self.ui.Run()

  def _RunTest(self):
    """Main routine for ALS test."""
    media_utils.MediaMonitor('usb-serial', None).Start(
        on_insert=self._OnU2SInsertion, on_remove=self._OnU2SRemoval)

    if self.args.assume_chamber_connected:
      self._SetFixtureStatus(FIXTURE_STATUS.CONNECTED)

    self._PostInternalQueue(EventType.START_TEST)

    # Loop to repeat the test until user chooses 'Exit Test'.  For module-level
    # testing, it may test thousands of DUTs without leaving the test. The test
    # passes or fails depending on the last test result.
    success, fail_msg = False, None
    while True:
      event = self._PopInternalQueue(wait=True)
      if event.event_type == EventType.START_TEST:
        try:
          with kbd_leds.Blinker(LED_PATTERN):
            if self.args.assume_chamber_connected:
              self._SetupFixture()

            self._ALSTest()

        except Exception as e:
          success, fail_msg = False, e.message
          self._ShowTestStatus(
              i18n.NoTranslation('ALS: FAIL %r' % fail_msg), style=STYLE_FAIL)
        else:
          success = True
          self._ShowTestStatus(i18n.NoTranslation('ALS: PASS'),
                               style=STYLE_PASS)
        finally:
          self._PostInternalQueue(EventType.EXIT_TEST)
      elif event.event_type == EventType.EXIT_TEST:
        if success:
          self.ui.Pass()
        else:
          self.fail('Test ALS failed - %r.' % fail_msg)
        break
      else:
        raise ValueError('Invalid event type.')

  def _PostInternalQueue(self, event_type, aux_data=None):
    """Posts an event to internal queue.

    Args:
      event_type: EventType.
      aux_data: Extra data.
    """
    self.internal_queue.put(InternalEvent(event_type, aux_data))

  def _PopInternalQueue(self, wait):
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

  def _ShowTestStatus(self, msg, style=STYLE_INFO):
    """Shows test status.

    Args:
      msg: i18n text.
      style: CSS style.
    """
    label = i18n_test_ui.MakeI18nLabelWithClass(msg, style)
    self.ui.SetHTML(label, id=ID_TEST_STATUS)
