# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(stimim): use DUT API

"""A factory test for ambient light sensor.

Description
-----------
Tests that ambient light sensor reacts to both darkening by covering with
finger as well as brightening by shining with flashlight.

Test Procedure
--------------
When the test starts, all subtests will be listed on the screen.  Operator
needs to press ``SPACE`` to start subtests.

After ``SPACE`` is pressed, the first subtest will become ``ACTIVE`` and
operator should follow the instruction shown on the screen, e.g. "Cover light
sensor with finger".  The pytest will keep polling light sensor value, as soon
as the  value meets the requirement, the subtest will be marked as ``PASSED``
and next subtest will become ``ACTIVE``  When all subtests are ``PASSED`` the
test will pass and stop.

Dependency
----------
The pytest requires ALS driver to expose sensor value as a file under sysfs.  By
default, the pytest finds the sensor value file with path
``/sys/bus/iio/devices/*/illuminance0_raw``.


Examples
--------
Minimum runnable example::

  {
    "pytest_name": "light_sensor"
  }

This will read ALS value from ``/sys/bus/iio/devices/*/illuminance0_raw``.
There will be 3 subtests,

1. ``'Light sensor dark'`` (below 4)
2. ``'Light sensor exact'`` (between 10 and 15)
3. ``'Light sensor light'`` (above 200)

Unfortunately, in most of the case, this does not work for you, because

* the exposed sysfs file has different name
* scale of the sensor value is different

For example, the arguments for your board might be::

  {
    "pytest_name": "light_sensor",
    "args": {
      "subtest_list": [
        "Light sensor dark",
        "Light sensor exact",
        "Light sensor light"
      ],
      "subtest_cfg": {
        "Light sensor exact": {
          "between": [60, 300]
        },
        "Light sensor light": {
          "above": 500
        },
        "Light sensor dark": {
          "below": 30
        }
      },
      "device_input": "in_illuminance_raw",
      "subtest_instruction": {
        "Light sensor exact": "i18n! Remove finger from light sensor",
        "Light sensor light": "i18n! Shine light sensor with flashlight",
        "Light sensor dark": "i18n! Cover light sensor with finger"
      }
    }
  }

Note that you have to specify ``subtest_list``, ``subtests_instruction``,
``subtest_cfg`` at the same time.
"""

import logging
import math
import os
import time

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


_DEFAULT_SUBTEST_LIST = ['Light sensor dark',
                         'Light sensor exact',
                         'Light sensor light']
_DEFAULT_SUBTEST_CFG = {'Light sensor dark': {'below': 4},
                        'Light sensor exact': {'between': (10, 15)},
                        'Light sensor light': {'above': 200}}
_DEFAULT_SUBTEST_INSTRUCTION = {
    'Light sensor dark': _('Cover light sensor with finger'),
    'Light sensor exact': _('Remove finger from light sensor'),
    'Light sensor light': _('Shine light sensor with flashlight')}

_DEFAULT_DEVICE_PATH = '/sys/bus/iio/devices/*/'
_DEFAULT_DEVICE_INPUT = 'illuminance0_raw'


class iio_generic:
  """Object to interface to ambient light sensor over iio.

  Properties:
    self._rd : the device file path
    self._init_cmd : command to initial device file
    self._min : minimum value of device output
    self._max : maximum value of device output
    self._mindelay : delay between each read action
  """

  def __init__(self, device_path, device_input, range_value, init_cmd,
               device_name, device):
    """Initial light sensor object.

    Args:
      device_path: light sensor device path
      device_input: file exports light sensor value
      range_value: reference device_path/range_available file to
                   set one of valid value (1000, 4000, 16000, 64000).
                   None means no value is set.
      init_cmd: initial command to setup light sensor device
    """
    self._dut = device
    if device_path is None:
      device_path = _DEFAULT_DEVICE_PATH

    if '*' in device_path:
      # use glob to find devices which contain device_input.
      matches = {}
      for input_path in self._dut.Glob(os.path.join(device_path, device_input)):
        path = os.path.dirname(input_path)
        try:
          name = self._dut.ReadFile(os.path.join(path, 'name')).rstrip()
        except Exception:
          name = None
        matches.update({path: name})

      if device_name is not None:
        filtered_matches = {
            path: name for path, name in matches.items() if name == device_name}
      else:
        filtered_matches = matches
      if not filtered_matches:
        raise ValueError(
            'Cannot find any light sensor from %r. '
            'matches: %r, filtered_matches: %r'
            % (device_path, matches, filtered_matches))
      if len(filtered_matches) > 1:
        raise ValueError(
            'More than one light sensor found from %r. '
            'matches: %r, filtered_matches: %r'
            % (device_path, matches, filtered_matches))
      device_path, device_name = list(filtered_matches.items())[0]
    else:
      try:
        name = self._dut.ReadFile(os.path.join(device_path, 'name')).rstrip()
      except Exception:
        name = None
      if device_name is not None:
        if device_name != name:
          raise ValueError(
              'The name of %s is %s but configure as %s'
              % (device_path, name, device_name))
      else:
        device_name = name

    logging.info('Select light sensor %s(%s)', device_path, device_name)

    # initial values
    self._rd = os.path.join(device_path, device_input)
    self._range_setting = os.path.join(device_path, 'range')
    self._calibrate = os.path.join(device_path, 'calibrate')
    self._init_cmd = init_cmd
    self._min = 0
    self._max = math.pow(2, 16)
    self._mindelay = 0.178

    if not os.path.isfile(self._rd):
      self.Config()

    if range_value is not None:
      if range_value not in (1000, 4000, 16000, 64000):
        raise ValueError('Range value is invalid: %d' % range_value)

      self._dut.WriteFile(self._range_setting, '%d\n' % range_value)

    ambient = self.Read('mean', delay=0, samples=10)
    logging.info('ambient light sensor = %d', ambient)

  def Config(self):
    """Creates device node if device does not exist."""
    if self._init_cmd:
      process_utils.Spawn(self._init_cmd, check_call=True)
    if not os.path.isfile(self._rd):
      raise ValueError('Cannot create %s' % self._rd)
    val = self.Read('first', samples=1)
    if val <= self._min or val >= self._max:
      raise ValueError('Failed initial read')

  def _WriteCalibrate(self, value):
    """Write calibrate value."""
    try:
      self._dut.WriteFile(self._calibrate, value)
    except Exception:
      logging.info('Unable to write to %s', self._calibrate)

  def Start(self):
    """Starts to catch in_illuminance_raw."""
    self._WriteCalibrate('1')

  def Stop(self):
    """Stops catching in_illuminance_raw."""
    self._WriteCalibrate('0')

  def Read(self, param, delay=None, samples=1):
    """Reads the light sensor and return value based on param

    Args:
      param: string describing type of value to return.  Valid
              strings are 'mean' | 'min' | 'max' | 'raw' | 'first'
      delay: delay between samples in seconds.  0 means as fast as possible
      samples: total samples to read.  O means infinite

    Returns:
      The value of light sensor

    Raises:
      ValueError if param is invalid.
    """
    count = 0
    buffers = []
    if delay is None:
      delay = self._mindelay
    while True:
      try:
        value = int(self._dut.ReadFile(self._rd).split('\n', 1)[0])
        buffers.append(value)
        count += 1
        time.sleep(delay)
        if count == samples:
          break
      except IOError:
        continue
    if param == 'mean':
      return sum(buffers) // len(buffers)
    if param == 'max':
      return max(buffers)
    if param == 'min':
      return min(buffers)
    if param == 'raw':
      return buffers
    if param == 'first':
      return buffers[0]
    raise ValueError('Illegal value %s for type' % type)


class LightSensorTest(test_case.TestCase):
  """Tests light sensor."""
  ARGS = [
      Arg('device_path', str, 'device path', default=None),
      Arg('device_name', str, 'device name', default=None),
      Arg('device_input', str, 'device input file',
          default=_DEFAULT_DEVICE_INPUT),
      Arg('timeout_per_subtest', int, 'timeout for each subtest', default=10),
      Arg('subtest_list', list, 'subtest list', default=None),
      Arg('subtest_cfg', dict, 'subtest configuration', default=None),
      Arg('subtest_instruction', dict, 'subtest instruction', default=None),
      Arg('check_per_subtest', int, 'check times for each subtest', default=3),
      Arg('init_command', list, 'Setup device command', default=None),

      # Special parameter for ISL 29018 light sensor
      Arg('range_value', int, 'one of value (1000, 4000, 16000, 64000)',
          default=None),
  ]

  def setUp(self):
    self._device = device_utils.CreateDUTInterface()
    self._als = iio_generic(self.args.device_path, self.args.device_input,
                            self.args.range_value, self.args.init_command,
                            self.args.device_name, self._device)

    subtest_args = [
        self.args.subtest_list, self.args.subtest_cfg,
        self.args.subtest_instruction
    ]
    if all(subtest_args):
      self._subtest_list = self.args.subtest_list
      self._subtest_cfg = self.args.subtest_cfg
      self._subtest_instruction = self.args.subtest_instruction
    elif any(subtest_args):
      raise ValueError(
          'Missing some of subtest_list, subtest_cfg or subtest_instruction.')
    else:
      self._subtest_list = _DEFAULT_SUBTEST_LIST
      self._subtest_cfg = _DEFAULT_SUBTEST_CFG
      self._subtest_instruction = _DEFAULT_SUBTEST_INSTRUCTION

    self._timeout_per_subtest = self.args.timeout_per_subtest
    self._iter_req_per_subtest = self.args.check_per_subtest

    for test_idx, name in enumerate(self._subtest_list):
      instruction = self._subtest_instruction[name]
      desc = '%s (%s)' % (
          name, self.GetConfigDescription(self._subtest_cfg[name]))
      html = [
          '<div class="task">',
          '<div id="title{idx}">'.format(idx=test_idx), instruction, '</div>'
          '<div class="desc-row">',
          '<div id="desc{idx}" class="desc">'.format(idx=test_idx),
          test_ui.Escape(desc), '</div>'
          '<div id="result{idx}" class="result">UNTESTED</div>'.format(
              idx=test_idx),
          '</div>', '</div>'
      ]
      self.ui.SetHTML(html, id='tasks', append=True)

    # Group checker and details for Testlog.
    self._group_checker = testlog.GroupParam(
        'light', ['name', 'elapsed', 'light'])
    testlog.UpdateParam('name', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('light', description=('Light sensor values over time'))
    testlog.UpdateParam('elapsed', value_unit='seconds')

  def GetConfigDescription(self, cfg):
    if 'above' in cfg:
      return 'Input > %d' % cfg['above']
    if 'below' in cfg:
      return 'Input < %d' % cfg['below']
    if 'between' in cfg:
      return '%d < Input < %d' % tuple(cfg['between'])
    raise ValueError('Unknown type in subtest configuration')

  def tearDown(self):
    self._als.Stop()

  def runTest(self):
    # If we put self._als.Start() in setUp and something throws an exception in
    # setUp then self._als.Stop() would not be executed.
    self._als.Start()
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
    self.ui.HideElement('space-prompt')
    self.ui.StartFailingCountdownTimer(
        self._timeout_per_subtest * len(self._subtest_list))

    for idx, name in enumerate(self._subtest_list):
      self.ui.SetHTML('ACTIVE', id='result%d' % idx)
      current_iter_remained = self._iter_req_per_subtest
      cumulative_val = 0
      start_time = time.time()
      while True:
        val = self._als.Read('mean', samples=5, delay=0)
        self.ui.SetHTML('Input: %d' % val, id='input')

        cfg = self._subtest_cfg[name]
        passed = False
        with self._group_checker:
          testlog.LogParam('name', name)
          testlog.LogParam('elapsed', time.time() - start_time)
          if 'above' in cfg:
            passed = testlog.CheckNumericParam('light', val, min=cfg['above'])
            logging.info('%s checking "above" %d > %d',
                         'PASSED' if passed else 'FAILED',
                         val, cfg['above'])
          elif 'below' in cfg:
            passed = testlog.CheckNumericParam('light', val, max=cfg['below'])
            logging.info('%s checking "below" %d < %d',
                         'PASSED' if passed else 'FAILED',
                         val, cfg['below'])
          elif 'between' in cfg:
            lb, ub = cfg['between']
            passed = testlog.CheckNumericParam('light', val, min=lb, max=ub)
            logging.info('%s checking "between" %d < %d < %d',
                         'PASSED' if passed else 'FAILED',
                         lb, val, ub)
          else:
            self.fail('subtest_cfg doesn\'t have "above", "below" or "between"')

        if passed:
          cumulative_val += val
          current_iter_remained -= 1
          if not current_iter_remained:
            self.ui.SetHTML('PASSED', id='result%d' % idx)
            mean_val = cumulative_val // self._iter_req_per_subtest
            logging.info('Passed subtest "%s" with mean value %d.', name,
                         mean_val)
            break
        else:
          if current_iter_remained != self._iter_req_per_subtest:
            logging.info('Resetting iter count.')
          cumulative_val = 0
          current_iter_remained = self._iter_req_per_subtest

        self.Sleep(0.5)
