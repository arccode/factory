# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION : factory test of ambient light sensor.  Test that ALS reacts to
# both darkening by covering w/ finger as well as brightening.
# Roughly speaking:
# indoor ambient lighting: 20-100
# sunlight direct: 30k-60k
# flashlight direct: 5k-10k


import logging
import math
import os
import time
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils.process_utils import Spawn

_DEFAULT_SUBTEST_LIST = ['Light sensor dark',
                         'Light sensor exact',
                         'Light sensor light']
_DEFAULT_SUBTEST_CFG = {'Light sensor dark': {'below': 4},
                        'Light sensor exact': {'between': (10, 15)},
                        'Light sensor light': {'above': 200}}
_DEFAULT_SUBTEST_INSTRUCTION = {
  'Light sensor dark': 'Cover light sensor with finger',
  'Light sensor exact': 'Remove finger from light sensor',
  'Light sensor light': 'Shine light sensor with flashlight'}

_DEFAULT_DEVICE_PATH = '/sys/bus/iio/devices/iio:device0/'
_DEFAULT_DEVICE_INPUT = 'illuminance0_input'

_MSG_PROMPT_FMT = """
    Use indicated light source to pass each subtest<br>
    Hit "space" to begin...<br><br>
"""

_ID_CONTAINER = 'light-sensor-container'
_ID_COUNTDOWN_TIMER = 'light-sensor-timer'

_CSS_LIGHT_SENSOR_TEST = """
  #light-sensor-timer { font-size: 1.5em; color: red; }
  .light-sensor-info { font-size: 1.5em; }
  .light-sensor-desc {font-size: 1.5em; color: green; }
"""

_JS_LIGHT_SENSOR_TEST = """
window.onkeydown = function(event) {
  if (event.keyCode == 32) {
    test.sendTestEvent("StartCountDown",{});
    window.onkeydown = null;
  }
}
"""

class iio_generic():
  """
  Object to interface to ambient light sensor over iio.

  Properties:
    self._rd : the device file path
    self._init : command to initial device file
    self._min : minimum value of device output
    self._max : maximum value of device output
    self._mindelay : delay between each read action
    self._ui : UI object
  """

  def __init__(self, device_path, device_input, range_value, ui):
    # initial values
    self._rd = device_path + device_input
    self._range_setting = device_path + 'range'
    self._init = ''
    self._min = 0
    self._max = math.pow(2, 16)
    self._mindelay = 0.178
    self._ui = ui

    if not os.path.isfile(self._rd):
      self.Config()

    if range_value is not None:
      with open(self._range_setting, 'w') as f:
        f.write('%d\n' % range_value)

    ambient = self.Read('mean', delay=0, samples=10)
    logging.info('ambient light sensor = %d', ambient)

  def Config(self):
    """
    Creates device node if device does not exist
    """
    if self._init:
      Spawn([self._init], check_call=True)
    if not os.path.isfile(self._rd):
      self._ui.Fail(self._init + ' did not create ' + self._rd)
    val = self.Read('first', samples=1)
    if val <= self._min or val >= self._max:
      self._ui.Fail('Failed initial read\n')

  def Read(self, param, delay=None, samples=1):
    """
    Reads the light sensor and return value based on param

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
        with open(self._rd, "r") as f:
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
    if param is 'mean':
      return sum(buffers) / len(buffers)
    elif param is 'max':
      return max(buffers)
    elif param is 'min':
      return min(buffers)
    elif param is 'raw':
      return buffers
    elif param is 'first':
      return buffers[0]
    else:
      raise ValueError('Illegal value %s for type' % type)


class LightSensorTest(unittest.TestCase):
  ARGS = [
    Arg('device_path', str, 'device path', _DEFAULT_DEVICE_PATH, optional=True),
    Arg('device_input', str, 'device input file', _DEFAULT_DEVICE_INPUT,
      optional=True),
    Arg('timeout_per_subtest', int, 'timeout for each subtest', 10,
      optional=True),
    Arg('subtest_list', list, 'subtest list', None, optional=True),
    Arg('subtest_cfg', dict, 'subtest configuration', None, optional=True),
    Arg('subtest_instruction', dict, 'subtest instruction', None,
      optional=True),
    Arg('range_value', int, 'subtest configuration', None, optional=True),
    Arg('check_per_subtest', int, 'check times for each subtest', 3,
      optional=True),
  ]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self._als = iio_generic(self.args.device_path, self.args.device_input,
        self.args.range_value, self.ui)
    StartDaemonThread(target=self.MonitorSensor)

    self.ui.AppendCSS(_CSS_LIGHT_SENSOR_TEST)
    self.ui.RunJS(_JS_LIGHT_SENSOR_TEST)
    self.ui.SetHTML(_MSG_PROMPT_FMT, id=_ID_CONTAINER)

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

    self._tested = 0
    self._started = False
    self._active_subtest = self._subtest_list[0]

    test = 0
    for name in self._subtest_list:
      self.ui.SetHTML(self._subtest_instruction[name], id="title%d" % test)
      desc = "%s (%s)" % (name,
          self.GetConfigDescription(self._subtest_cfg[name]))
      self.ui.SetHTML(desc, id="desc%d" % test)
      self.ui.SetHTML(" : UNTESTED", id="result%d" % test)
      test += 1

  def StartCountDown(self, event): # pylint: disable=W0613
    self._started = True
    self._active_subtest = self._subtest_list[0]
    self.ui.SetHTML(" : ACTIVE",
        id="result%d" % self._tested)
    StartCountdownTimer(self._timeout_per_subtest * len(self._subtest_list),
                        self.TimeoutHandler,
                        self.ui,
                        _ID_COUNTDOWN_TIMER)

  def NextSubtest(self):
    self._tested += 1
    if self._tested >= len(self._subtest_list):
      self.ui.Pass()
      return False
    self._active_subtest = self._subtest_list[self._tested]
    self.ui.SetHTML(" : ACTIVE",
        id="result%d" % self._tested)
    self._current_iter_remained = self._iter_req_per_subtest
    self._cumulative_val = 0
    return True

  def TimeoutHandler(self):
    self.ui.SetHTML(" : FAILED", id="result%d" % self._tested)
    self.ui.Fail('Timeout on subtest "%s"' % self._active_subtest)

  def PassOneIter(self, name):
    self._current_iter_remained -= 1
    if self._current_iter_remained is 0:
      self.ui.SetHTML(" : PASSED", id="result%d" % self._tested)
      self._current_iter_remained = self._iter_req_per_subtest
      mean_val = self._cumulative_val / self._iter_req_per_subtest
      logging.info('Passed subtest "%s" with mean value %d.',
                  name, mean_val)
      if not self.NextSubtest():
        return

  def CheckSensorEvent(self):
    val = self._als.Read('mean', samples=5, delay=0)

    if self._started:
      name = self._active_subtest
      cfg = self._subtest_cfg[name]
      passed = False
      if 'above' in cfg:
        if val > cfg['above']:
          logging.info('Passed checking "above" %d > %d',
                       val, cfg['above'])
          passed = True
      elif 'below' in cfg:
        if val < cfg['below']:
          logging.info('Passed checking "below" %d < %d',
                       val, cfg['below'])
          passed = True
      elif 'between' in cfg:
        lb, ub = cfg['between']
        if val > lb and val < ub:
          logging.info('Passed checking "between" %d < %d < %d',
                       lb, val, ub)
          passed = True
      if passed:
        self._cumulative_val += val
        self.PassOneIter(name)
      else:
        if self._current_iter_remained != self._iter_req_per_subtest:
          logging.info('Resetting iter count.')
        self._cumulative_val = 0
        self._current_iter_remained = self._iter_req_per_subtest

    self.ui.SetHTML("Input: %d" % val, id="sensor_input")
    return True

  def GetConfigDescription(self, cfg):
    if 'above' in cfg:
      return 'Input > %d' % cfg['above']
    elif 'below' in cfg:
      return 'Input < %d' % cfg['below']
    elif 'between' in cfg:
      return '%d < Input < %d' % cfg['between']
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
    self.ui.AddEventHandler('StartCountDown', self.StartCountDown)
    self.ui.Run()
