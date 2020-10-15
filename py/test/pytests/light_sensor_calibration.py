# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=line-too-long
"""Calibration test for light sensor (a chamber is needed).

Description
-----------
This is a station-based test which calibrates light sensors.
The test controls a light chamber to switch light intensity between different
light preset and reads the value from the light sensor of a DUT.

The calibration method is linear regression. The test samples multiple
data points (e.g., LUX1, LUX2) and find out a new linear equation to fit the
validating data point (e.g., LUX3). The calibrated coefficients scale factor and
bias will be saved to the VPD.

The default chamber connection driver is PL2303 over RS232. You can speicify a
new driver to ``chamber_conn_params``. You also need to provide the
``chamber_cmd`` with which a station can command the light chamber.

Besides the arguments, there are still many configurations in the
light_sensor_calibration.json. For examples:

  {
    "version": "v0.01",
    "light_seq": ["LUX1", "LUX2", "LUX3"],
    "n_samples": 5,
    "read_delay": 2.0,
    "light_delay": 6.0,
    "luxs": [40, 217],
    "validating_light": "LUX3",
    "validating_lux": 316,
    "validating_err_limit": 0.2,
    "force_light_init": false

  }

The most important entries are ``luxs`` and ``validating_lux``. They are the
preset illuminance value of a light chamber fixture. You need a lux meter
to evaluate the preset light settings from the light chamber fixture to get
these values. After you have these values, don't forget to update the runtime
configuration by calling
``cros.factory.utils.config_utils.SaveRuntimeConfig('light_sensor_calibration', new_config)``
so that you have the correct preset light information. There are many things
that influence the preset light value of the light chamber. It could be the
unstable elecrtic environment or if the light chamber's bulb is broken.

Test Procedure
--------------
This is an automated test. Before you start the test, prepare the
physical setup and calibrate the light chamber itself by a lux meter:

1. Connects the station and the DUT.
2. Connects the station and the light chamber.
3. Press start test.
4. After finishing the test, disconnects the station and the DUT.

Dependency
----------
- A light chamber with at least three luminance settings.

Examples
--------
To automatically calibrate the light_sensor with the given ``chamber_cmd``, add
this into test list::

  {
    "pytest_name": "light_sensor_calibration",
    "args": {
      "control_chamber": true,
      "assume_chamber_connected": true,
      "chamber_cmd": {
        "LUX1": [
          [
            "LUX1_ON",
            "LUX1_READY"
          ]
        ],
        "LUX2": [
          [
            "LUX2_ON",
            "LUX2_READY"
          ]
        ],
        "LUX3": [
          [
            "LUX3_ON",
            "LUX3_READY"
          ]
        ],
        "OFF": [
          [
            "OFF",
            "OFF_READY"
          ]
        ]
      }
    }
  }

To debug and use a mocked light chamber::

  {
    "pytest_name": "light_sensor_calibration",
    "args": {
      "control_chamber": true,
      "mock_mode": true
    }
  }

To manually switch chamber light::

  {
    "pytest_name": "light_sensor_calibration",
    "args": {
      "control_chamber": false
    }
  }

Trouble Shooting
----------------
If you found error related to load configuration file:

- This is probably your runtime config format is incorrect.

If you found error connecting to light chamber:

1. Make sure the chamber and station are connected.
2. Make sure the dongle is correct one. If you are not using the dongle with
   PL2303 driver, you need to provide one.

If you found the calibrated coefficients are skewd:

1. This is probably you don't calibrate the light chamber recently.
"""

from collections import namedtuple
import json
import logging
import time

import numpy as np

from cros.factory.device import ambient_light_sensor
from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.fixture import fixture_connection
from cros.factory.test.fixture.light_sensor import light_chamber
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test.utils import kbd_leds
from cros.factory.test.utils import media_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


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


class ALSFixture(test_case.TestCase):
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
          "either a dict, defaults to None", default=None),
      Arg('chamber_cmd', dict, 'A dict for name of lightning to a '
          '[cmd, cmd_response].'),
      Arg('chamber_n_retries', int, 'Number of retries when connecting.',
          default=10),
      Arg('chamber_retry_delay', int, 'Delay between connection retries.',
          default=2),

      # test environment
      Arg('mock_mode', bool, 'Mock mode allows testing without a fixture.',
          default=False),
      Arg('config_dict', dict, 'The config dictionary. '
          'If None, then the config is loaded by config_utils.LoadConfig().',
          default=None),
      Arg('keep_raw_logs', bool,
          'Whether to attach the log by Testlog',
          default=True),

  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

    try:
      self.als_controller = self.dut.ambient_light_sensor.GetController()
    except Exception as e:
      self._LogFailure(FAIL_ALS_NOT_FOUND,
                       'Error getting ALS controller: %s' % str(e))
      raise

    # Loads config.
    try:
      self.config = self.args.config_dict or config_utils.LoadConfig()
      if self.config is None:
        raise ValueError('No available configuration.')
      self._LogConfig()
    except Exception as e:
      logging.exception('Error logging config file: %s', str(e))
      raise

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
          script = {k.strip(): v.strip()
                    for k, v in sum(self.args.chamber_cmd.values(), [])}
          self.fixture_conn = fixture_connection.MockFixtureConnection(script)
        else:
          self.fixture_conn = fixture_connection.SerialFixtureConnection(
              **chamber_conn_params)

      self.chamber = light_chamber.LightChamber(
          fixture_conn=self.fixture_conn, fixture_cmd=self.args.chamber_cmd)
    except Exception as e:
      self._LogFailure(FAIL_CHAMBER_ERROR,
                       'Error setting up ALS chamber: %s' % str(e))

    self.all_sampled_lux = []  # mean of sampled lux for each light
    self.scale_factor = None  # value of calibrated scale factor
    self.bias = None  # value of calibrated bias
    self.light_index = -1  # ALS test stage

    self.monitor = media_utils.MediaMonitor('usb-serial', None)

    self.ui.SetTitle(_('ALS Sensor Calibration'))

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'lux_value', ['name', 'value', 'elapsed'])

  def _Log(self, text):
    """Custom log function to log."""
    logging.info(text)
    session.console.info(text)

  def _LogArgument(self, key, value, description):
    testlog.AddArgument(key, value, description)
    self._Log("%s=%s" % (key, value))

  def _LogConfig(self):
    if self.args.keep_raw_logs:
      testlog.AttachContent(
          content=json.dumps(self.config),
          name='light_sensor_calibration_config.json',
          description='json of light sensor calibration config')

  def _LogFailure(self, code, details):
    testlog.AddFailure(code, details)
    message = 'FAIL %r: %r' % (code, details)
    logging.exception(message)
    session.console.info(message)

  def _ALSTest(self):
    try:
      self._ShowTestStatus(_('Cleaning up calibration values'))
      if not self.args.mock_mode:
        self.als_controller.CleanUpCalibrationValues()
    except Exception as e:
      self._LogFailure(FAIL_ALS_CLEAN, 'Error cleaning up calibration values:'
                       ' %s' % str(e))
      raise

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
                         (self.light_index, light_name, str(e)))
        raise

    try:
      self._ShowTestStatus(_('Checking ALS ordering'))
      self._CheckALSOrdering()
    except Exception as e:
      self._LogFailure(FAIL_ALS_ORDER,
                       'Error checking als ordering: %s' % str(e))
      raise


    try:
      self._ShowTestStatus(_('Calculating calibration coefficients'))
      self._CalculateCalibCoef()
    except Exception as e:
      self._LogFailure(FAIL_ALS_CALC, 'Error calculating calibration'
                       ' coefficient: %s' % str(e))
      raise

    try:
      self._ShowTestStatus(_('Saving calibration coefficients to VPD'))
      self._SaveCalibCoefToVPD()
    except Exception as e:
      self._LogFailure(FAIL_ALS_VPD, 'Error setting calibration'
                       ' coefficient to VPD: %s' % str(e))
      raise

    try:
      self._ShowTestStatus(_('Validating ALS'))
      light_name = self.config['validating_light']
      self._SwitchLight(light_name)
      self._ValidateALS(light_name)
    except Exception as e:
      self._LogFailure(FAIL_ALS_VALID,
                       'Error validating calibrated ALS: %s' % str(e))
      raise

  def _OnU2SInsertion(self, device):
    del device  # unused
    cnt = 0
    while cnt < self.args.chamber_n_retries:
      try:
        self._SetupFixture()
        self._SetFixtureStatus(FIXTURE_STATUS.CONNECTED)
        return
      except Exception:
        cnt += 1
        self._SetFixtureStatus(FIXTURE_STATUS.DISCONNECTED)
        self.Sleep(self.args.chamber_retry_delay)
    raise light_chamber.LightChamberError('Error connecting to light chamber')

  def _OnU2SRemoval(self, device):
    del device  # unused
    self._SetFixtureStatus(FIXTURE_STATUS.DISCONNECTED)

  def _SetFixtureStatus(self, status):
    if status == FIXTURE_STATUS.CONNECTED:
      style = 'color-good'
      label = _('Fixture Connected')
    elif status == FIXTURE_STATUS.DISCONNECTED:
      style = 'color-bad'
      label = _('Fixture Disconnected')
    else:
      raise ValueError('Unknown fixture status %s' % status)
    self.ui.SetHTML(
        ['<span class="%s">' % style, label, '</span>'], id='fixture-status')

  def _SetupFixture(self):
    """Initialize the communication with the fixture."""
    try:
      self.chamber.Connect()
    except Exception as e:
      self._LogFailure(FAIL_CHAMBER_ERROR, 'Error initializing the ALS fixture:'
                       ' %s' % str(e))
      raise
    self._Log('Test fixture successfully initialized.')

  def _SwitchLight(self, light):
    self._Log("Switching to lighting %s." % light)
    self._ShowTestStatus(
        i18n.StringFormat(_('Switching to lighting {name}'), name=light))
    try:
      self.chamber.SetLight(light)
    except Exception as e:
      self._LogFailure(FAIL_CHAMBER_ERROR,
                       'Error commanding ALS chamber: %s' % str(e))
      raise
    self.Sleep(self.config['light_delay'])

  def _SwitchToNextLight(self):
    self.light_index += 1
    if self.light_index >= len(self.config['luxs']):
      return False
    self._SwitchLight(self.config['light_seq'][self.light_index])
    return True

  def _SampleLuxValue(self, param_name, delay, samples):
    if self.args.mock_mode:
      return ALS_MOCK_VALUE
    try:
      buf = []
      start_time = time.time()
      for unused_i in range(samples):
        self.Sleep(delay)
        buf.append(self.als_controller.GetLuxValue())
        with self.group_checker:
          elapsed_time = time.time() - start_time
          testlog.LogParam('name', param_name)
          testlog.LogParam('value', buf[-1])
          testlog.LogParam('elapsed', elapsed_time)
          self._Log('%r: %r' % (elapsed_time, buf[-1]))
    except ambient_light_sensor.AmbientLightSensorException as e:
      logging.exception('Error reading ALS value: %s', str(e))
      raise
    return float(np.mean(buf))

  def _SampleALS(self, light_name):
    param_name = 'Calibrating' + light_name
    testlog.UpdateParam(
        param_name,
        description=('Sampled calibrating lux for %s over time' % light_name),
        value_unit='lx')
    sampled_lux = self._SampleLuxValue(
        param_name, self.read_delay, self.n_samples)
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
    testlog.UpdateParam(
        'ValidatingLux',
        description=('Sampled validating lux for %s over time' % light_name),
        value_unit='lx')
    sampled_vlux = self._SampleLuxValue(
        'ValidatingLux', self.read_delay, self.n_samples)
    preset_vlux = float(self.config['validating_lux'])
    self._LogArgument('Preset%s' % light_name, preset_vlux,
                      'Preset validating lux value.')
    self._LogArgument('MeanValidatingLux', sampled_vlux,
                      'Mean of sampled validating lux value.')
    testlog.UpdateParam(
        name='ValidatingLuxMean',
        description=('Mean of sampled validating lux for %s' % light_name),
        value_unit='lx')
    err_limit = float(self.config['validating_err_limit'])
    lower_bound = preset_vlux * (1 - err_limit)
    upper_bound = preset_vlux * (1 + err_limit)
    result = testlog.CheckNumericParam(
        'ValidatingLuxMean',
        sampled_vlux,
        min=lower_bound,
        max=upper_bound)
    self._Log('%s ValidatingLuxMean: %r (min=%s, max=%s)' %
              (result, sampled_vlux, lower_bound, upper_bound))

    if not result and not self.args.mock_mode:
      raise ValueError('Error validating calibrated als, got %s out of'
                       ' range (%s, %s)' % (sampled_vlux, lower_bound,
                                            upper_bound))

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
      samples = list(zip(xs[1:], ys[1:]))
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

  def tearDown(self):
    self.monitor.Stop()

  def runTest(self):
    """Main routine for ALS test."""
    self.monitor.Start(
        on_insert=self._OnU2SInsertion, on_remove=self._OnU2SRemoval)

    if self.args.assume_chamber_connected:
      self._SetFixtureStatus(FIXTURE_STATUS.CONNECTED)

    try:
      with kbd_leds.Blinker(LED_PATTERN):
        if self.args.assume_chamber_connected:
          self._SetupFixture()

        self._ALSTest()

    except Exception as e:
      fail_msg = str(e)
      self._ShowTestStatus(
          i18n.NoTranslation('ALS: FAIL %r' % fail_msg), style='color-bad')
      self.fail('Test ALS failed - %r.' % fail_msg)
    else:
      self._ShowTestStatus(i18n.NoTranslation('ALS: PASS'),
                           style='color-good')

  def _ShowTestStatus(self, msg, style='color-idle'):
    """Shows test status.

    Args:
      msg: i18n text.
      style: CSS style.
    """
    self.ui.SetHTML(
        ['<span class="%s">' % style, msg, '</span>'], id='test-status')
