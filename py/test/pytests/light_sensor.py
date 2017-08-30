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
``/sys/bus/iio/devices/*/illuminance0_input``.


Examples
--------
Minimum runnable example::

    OperatorTest(pytest_name='light_sensor')

This will read ALS value from ``/sys/bus/iio/devices/*/illuminance0_input``.
There will be 3 subtests,

1. ``'Light sensor dark'`` (belaw 4)
2. ``'Light sensor exact'`` (between 10 and 15)
3. ``'Light sensor light'`` (above 200)

Unfortunately, in most of the case, this does not work for you, because

* the exposed sysfs file has different name
* scale of the sensor value is different

For example, the arguments for your board might be::

    OperatorTest(
        pytest_name='light_sensor',
        dargs={
            'device_input': 'in_illuminance_raw',
            'subtest_list': [
                'Light sensor dark', 'Light sensor exact', 'Light sensor light'
            ],
            'subtest_instruction': {
                'Light sensor dark': _('Cover light sensor with finger'),
                'Light sensor exact': _('Remove finger from light sensor'),
                'Light sensor light': _('Shine light sensor with flashlight'),
            },
            'subtest_cfg': {
                'Light sensor dark': {'below': 30},
                'Light sensor exact': {'between': (60, 300)},
                'Light sensor light': {'above': 500}
            }
        })

Note that you have to specify ``subtest_list``, ``subtests_instruction``,
``subtest_cfg`` at the same time.
"""

from __future__ import print_function

import glob
import logging
import math
import os
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import countdown_timer
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
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
_DEFAULT_DEVICE_INPUT = 'illuminance0_input'

_MSG_PROMPT_FMT = i18n_test_ui.MakeI18nLabel(
    'Use indicated light source to pass each subtest<br>'
    'Hit "space" to begin...')

_HTML = """
<div id="light-sensor-container">
  <div id="light-sensor-prompt"></div>
  <div id="light-sensor-tasks"></div>
  <div id="light-sensor-info">
    <div id="light-sensor-input"></div>
    <div id="light-sensor-timer"></div>
  </div>
</div>
"""


class iio_generic(object):
  """Object to interface to ambient light sensor over iio.

  Properties:
    self._rd : the device file path
    self._init_cmd : command to initial device file
    self._min : minimum value of device output
    self._max : maximum value of device output
    self._mindelay : delay between each read action
  """

  def __init__(self, device_path, device_input, range_value, init_cmd):
    """Initial light sensor object.

    Args:
      device_path: light sensor device path
      device_input: file exports light sensor value
      range_value: reference device_path/range_available file to
                   set one of valid value (1000, 4000, 16000, 64000).
                   None means no value is set.
      init_cmd: initial command to setup light sensor device
    """
    if device_path is None:
      device_path = _DEFAULT_DEVICE_PATH

    if '*' in device_path:
      # use glob to find correct path
      matches = glob.glob(os.path.join(device_path, device_input))
      assert matches, 'Cannot find any light sensor'
      assert len(matches) == 1, 'More than one light sensor found'
      device_path = os.path.dirname(matches[0])

    # initial values
    self._rd = os.path.join(device_path, device_input)
    self._range_setting = os.path.join(device_path, 'range')
    self._init_cmd = init_cmd
    self._min = 0
    self._max = math.pow(2, 16)
    self._mindelay = 0.178

    if not os.path.isfile(self._rd):
      self.Config()

    if range_value is not None:
      if range_value not in (1000, 4000, 16000, 64000):
        raise ValueError('Range value is invalid: %d' % range_value)

      with open(self._range_setting, 'w') as f:
        f.write('%d\n' % range_value)

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
        with open(self._rd, 'r') as f:
          value = int(f.readline().rstrip())
      except IOError:
        continue
      else:
        f.close()
        buffers.append(value)
        count += 1
        time.sleep(delay)
        if count == samples:
          break
    if param == 'mean':
      return sum(buffers) / len(buffers)
    elif param == 'max':
      return max(buffers)
    elif param == 'min':
      return min(buffers)
    elif param == 'raw':
      return buffers
    elif param == 'first':
      return buffers[0]
    else:
      raise ValueError('Illegal value %s for type' % type)


class LightSensorTest(unittest.TestCase):
  """Tests light sensor."""
  ARGS = [
      Arg('device_path', str, 'device path', optional=True),
      Arg('device_input', str, 'device input file', _DEFAULT_DEVICE_INPUT),
      Arg('timeout_per_subtest', int, 'timeout for each subtest', 10),
      Arg('subtest_list', list, 'subtest list', optional=True),
      Arg('subtest_cfg', dict, 'subtest configuration', optional=True),
      Arg('subtest_instruction', dict, 'subtest instruction', optional=True),
      Arg('check_per_subtest', int, 'check times for each subtest', 3),
      Arg('init_command', list, 'Setup device command', optional=True),

      # Special parameter for ISL 29018 light sensor
      Arg('range_value', int, 'one of value (1000, 4000, 16000, 64000)',
          optional=True),
  ]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)

    try:
      self._als = iio_generic(self.args.device_path, self.args.device_input,
                              self.args.range_value, self.args.init_command)
    except ValueError as e:
      self.ui.Fail(e)
      return

    self.ui.AppendCSSLink('light_sensor.css')
    self.ui.BindKey(test_ui.SPACE_KEY, self.StartCountDown, once=True)
    self.template.SetState(_HTML)
    self.ui.SetHTML(_MSG_PROMPT_FMT, id='light-sensor-prompt')

    # Initialize variables
    self._subtest_list = _DEFAULT_SUBTEST_LIST
    self._subtest_cfg = _DEFAULT_SUBTEST_CFG
    self._subtest_instruction = _DEFAULT_SUBTEST_INSTRUCTION
    self.GetSubtest(self.args.subtest_list, self.args.subtest_cfg,
                    self.args.subtest_instruction)

    self._timeout_per_subtest = self.args.timeout_per_subtest
    self._iter_req_per_subtest = self.args.check_per_subtest
    self._current_iter_remained = self._iter_req_per_subtest
    self._cumulative_val = 0

    self._current_test_idx = -1
    self._active_series = None
    self._started = False
    self._active_subtest = self._subtest_list[0]

    for test_idx, name in enumerate(self._subtest_list):
      instruction = i18n_test_ui.MakeI18nLabel(self._subtest_instruction[name])
      desc = '%s (%s)' % (
          name, self.GetConfigDescription(self._subtest_cfg[name]))
      html = (
          u'<div class="light-sensor-task">'
          u'<div id="title{idx}">{instruction}</div>'
          u'<div class="light-sensor-desc-row">'
          u'<div id="desc{idx}" class="light-sensor-desc">{desc}</div>'
          u'<div id="result{idx}" class="light-sensor-result">UNTESTED</div>'
          u'</div>'
          u'</div>').format(
              idx=test_idx, instruction=instruction, desc=desc)
      self.ui.SetHTML(html, id='light-sensor-tasks', append=True)

  def StartCountDown(self, event):
    del event  # Unused.
    self.NextSubtest()
    self._started = True
    countdown_timer.StartCountdownTimer(
        self._timeout_per_subtest * len(self._subtest_list),
        self.TimeoutHandler, self.ui, 'light-sensor-timer')

  def NextSubtest(self):
    self._current_test_idx += 1
    if self._current_test_idx >= len(self._subtest_list):
      self.ui.Pass()
      return
    self._active_subtest = self._subtest_list[self._current_test_idx]
    self._active_series = testlog.CreateSeries(
        name=self._active_subtest,
        description=('Light sensor values over time for subtest "%s"' %
                     self._active_subtest),
        key_unit='seconds')  # no value unit
    self.ui.SetHTML('ACTIVE', id='result%d' % self._current_test_idx)
    self._current_iter_remained = self._iter_req_per_subtest
    self._cumulative_val = 0

  def TimeoutHandler(self):
    self.ui.SetHTML('FAILED', id='result%d' % self._current_test_idx)
    self.ui.Fail('Timeout on subtest "%s"' % self._active_subtest)

  def PassOneIter(self, name):
    self._current_iter_remained -= 1
    if not self._current_iter_remained:
      self.ui.SetHTML('PASSED', id='result%d' % self._current_test_idx)
      self._current_iter_remained = self._iter_req_per_subtest
      mean_val = self._cumulative_val / self._iter_req_per_subtest
      logging.info('Passed subtest "%s" with mean value %d.', name, mean_val)
      self.NextSubtest()

  def CheckSensorEvent(self):
    val = self._als.Read('mean', samples=5, delay=0)

    if self._started:
      name = self._active_subtest
      cfg = self._subtest_cfg[name]
      passed = False
      if 'above' in cfg:
        passed = self._active_series.CheckValue(
            key=time.time(), value=val, min=cfg['above'])
        logging.info('%s checking "above" %d > %d',
                     'PASSED' if passed else 'FAILED',
                     val, cfg['above'])
      elif 'below' in cfg:
        passed = self._active_series.CheckValue(
            key=time.time(), value=val, max=cfg['below'])
        logging.info('%s checking "below" %d < %d',
                     'PASSED' if passed else 'FAILED',
                     val, cfg['below'])
      elif 'between' in cfg:
        lb, ub = cfg['between']
        passed = self._active_series.CheckValue(
            key=time.time(), value=val, min=lb, max=ub)
        logging.info('%s checking "between" %d < %d < %d',
                     'PASSED' if passed else 'FAILED',
                     lb, val, ub)
      if passed:
        self._cumulative_val += val
        self.PassOneIter(name)
      else:
        if self._current_iter_remained != self._iter_req_per_subtest:
          logging.info('Resetting iter count.')
        self._cumulative_val = 0
        self._current_iter_remained = self._iter_req_per_subtest

    self.ui.SetHTML('Input: %d' % val, id='light-sensor-input')

  def GetConfigDescription(self, cfg):
    if 'above' in cfg:
      return 'Input > %d' % cfg['above']
    elif 'below' in cfg:
      return 'Input < %d' % cfg['below']
    elif 'between' in cfg:
      return '%d < Input < %d' % tuple(cfg['between'])
    else:
      raise ValueError('Unknown type in subtest configuration')

  def GetSubtest(self, subtest_list, subtest_cfg, subtest_instruction):
    has_specified = (subtest_list or subtest_cfg or subtest_instruction)
    all_specified = (subtest_list and subtest_cfg and subtest_instruction)
    if has_specified and not all_specified:
      raise ValueError('Missing parameters of subtests.')
    if all_specified:
      self._subtest_list = subtest_list
      self._subtest_cfg = subtest_cfg
      self._subtest_instruction = subtest_instruction

  def MonitorSensor(self):
    while True:
      self.CheckSensorEvent()
      time.sleep(0.6)

  def runTest(self):
    self.ui.RunInBackground(self.MonitorSensor)
    self.ui.Run()
