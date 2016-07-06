# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests screen rotation through ChromeOS and accelerometer data.

Tests that ChromeOS properly rotates the screen when the device is physically
rotated in tablet mode, and also checks that the orientation matches up with
accelerometer data if configured.

Usage example::

    # Only test ChromeOS rotation value.
    OperatorTest(
        id='TabletRotation',
        label_zh=u'平板电脑旋转测试',
        pytest_name='tablet_rotation',
        dargs={
            'timeout_secs': HOURS_24,
            'prompt_flip_tablet': False,
            'prompt_flip_notebook': True,
            # Include to also check accelerometer data.
            # 'check_accelerometer': True,
            # 'degrees_to_orientations': {
            #      0: {'in_accel_x_base': -1,
            #            'in_accel_y_base': 0,
            #            'in_accel_z_base': 0,
            #            'in_accel_x_lid': -1,
            #            'in_accel_y_lid': 0,
            #            'in_accel_z_lid': 0},
            #      90: {'in_accel_x_base': 0,
            #             'in_accel_y_base': 1,
            #             'in_accel_z_base': 0,
            #             'in_accel_x_lid': 0,
            #             'in_accel_y_lid': 1,
            #             'in_accel_z_lid': 0},
            #      180: {'in_accel_x_base': 1,
            #              'in_accel_y_base': 0,
            #              'in_accel_z_base': 0,
            #              'in_accel_x_lid': 1,
            #              'in_accel_y_lid': 0,
            #              'in_accel_z_lid': 0},
            #      270: {'in_accel_x_base': 0,
            #              'in_accel_y_base': -1,
            #              'in_accel_z_base': 0,
            #              'in_accel_x_lid': 0,
            #              'in_accel_y_lid': -1,
            #              'in_accel_z_lid': 0}},
            #      'spec_offset': (92, 91 + 61),
            #      'spec_ideal_values': (0, 1024)})
        })
"""

import random
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.pytests.tablet_mode_ui import TabletModeUI
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.process_utils import StartDaemonThread


_DEFAULT_TIMEOUT = 30
_UNICODE_PICTURES = u'☃☺☎'
_TEST_DEGREES = [90, 180, 270, 0]
_POLL_ROTATION_INTERVAL = 0.1

_MSG_PROMPT_ROTATE_TABLET = test_ui.MakeLabel(
    'Rotate the tablet to correctly align the picture, holding it at an '
    'upright 90-degree angle.',
    u'竖立平板电脑使其垂直于桌面，并开始旋转到对齐图片。')

_ID_COUNTDOWN_TIMER = 'countdown-timer'
_ID_PROMPT = 'prompt'
_ID_PICTURE = 'picture'

_HTML_COUNTDOWN_TIMER = '<div id="%s" class="countdown-timer"></div>' % (
    _ID_COUNTDOWN_TIMER)
_HTML_BUILD_PICTURE = lambda degrees, picture: (
    '<span style="-webkit-transform: rotate(%sdeg);">%s</span>'
    % (degrees, picture))
_HTML = """
<div class="prompt" id="%s"></div>
<div class="picture" id="%s"></div>
""" % (_ID_PROMPT, _ID_PICTURE)

_CSS_COUNTDOWN_TIMER = """
.countdown-timer {
  position: absolute;
  bottom: .3em;
  right: .5em;
  font-size: 2em;
}
"""
_CSS = """
.prompt {
  font-size: 2em;
  margin-bottom: 1em;
}
.picture span {
  font-size: 15em;
  display: block;
}
"""


class TabletRotationTest(unittest.TestCase):
  """Tablet rotation factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT, optional=True),
      Arg('prompt_flip_tablet', bool,
          'Assume the notebook is not yet in tablet mode, and operator should '
          'first be instructed to flip it as such. (This is useful to unset if '
          'the previous test finished in tablet mode.)',
          default=True, optional=True),
      Arg('prompt_flip_notebook', bool,
          'After the test, prompt the operator to flip back into notebook '
          'mode. (This is useful to unset if the next test requires tablet '
          'mode.)',
          default=True, optional=True),
      Arg('check_accelerometer', bool,
          'In addition to checking the ChromeOS screen orientation, also check '
          'accelerometer data to ensure it reports the same orientation.',
          default=False, optional=True),
      Arg('degrees_to_orientations', dict,
          'Keys: degree of the orientation, limited to [0, 90, 180, 270]. '
          'Values: a dictionary containing orientation configuration.  Keys '
          'should be the name of the accelerometer signal. For example, '
          '"in_accel_x_base" or "in_accel_x_lid". The possible keys are '
          '"in_accel_(x|y|z)_(base|lid)". Values should be one of [0, 1, -1], '
          'representing the ideal value for gravity under such orientation.',
          default={}, optional=True),
      Arg('spec_offset', tuple,
          'A tuple of two integers, ex: (128, 230) '
          'indicating the tolerance for the digital output of sensors under '
          'zero gravity and one gravity. Those values are vendor-specific '
          'and should be provided by the vendor.', optional=True),
      Arg('spec_ideal_values', tuple,
          'A tuple of two integers, ex: (0, 1024) indicating the ideal value '
          'of digital output corresponding to 0G and 1G, respectively. For '
          'example, if a sensor has a 12-bit digital output and -/+ 2G '
          'detection range so the sensitivity is 1024 count/G. The value '
          'should be provided by the vendor.', optional=True),
      Arg('sample_rate_hz', int,
          'The sample rate in Hz to get raw data from '
          'accelerometers.', default=20, optional=True),
  ]

  def setUp(self):
    # args.check_accelerometer implies the following required arguments:
    #   degrees_to_orientations
    #   spec_offset
    #   spec_ideal_values
    self.dut = device_utils.CreateDUTInterface()
    self.accel_controller = None
    if self.args.check_accelerometer:
      if not all([self.args.degrees_to_orientations,
                  self.args.spec_offset,
                  self.args.spec_ideal_values]):
        self.fail('If running in check_accelerometer mode, please provide '
                  'arguments degrees_to_orientations, spec_offset '
                  'and spec_ideal_values.')
        return

      self.accel_controller = self.dut.accelerometer.GetController()

    self.ui = test_ui.UI()
    self.state = factory.get_state_instance()
    self.tablet_mode_ui = TabletModeUI(self.ui,
                                       _HTML_COUNTDOWN_TIMER,
                                       _CSS_COUNTDOWN_TIMER)

    # Create a thread to run countdown timer.
    StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Tablet rotation test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

    # Create a thread to control UI flow.
    def _UIFlow():
      if self.args.prompt_flip_tablet:
        self.tablet_mode_ui.AskForTabletMode(
            lambda _: self.TestRotationUIFlow())
      else:
        self.TestRotationUIFlow()
    StartDaemonThread(target=_UIFlow)

  def TestRotationUIFlow(self, degrees_targets=None):
    if degrees_targets is None:
      degrees_targets = _TEST_DEGREES

    for degrees_target in degrees_targets:
      # Initialize UI template, HTML and CSS.
      template = OneSection(self.ui)
      template.SetState(_HTML + _HTML_COUNTDOWN_TIMER)
      self.ui.AppendCSS(_CSS + _CSS_COUNTDOWN_TIMER)

      try:
        self._PromptAndWaitForRotation(degrees_target)
      except Exception as e:
        self.ui.Fail(e.msg)
        return

      self.tablet_mode_ui.FlashSuccess()

    if self.args.prompt_flip_notebook:
      self.tablet_mode_ui.AskForNotebookMode(
          lambda _: self.ui.Pass())
    else:
      self.ui.Pass()


  def _PromptAndWaitForRotation(self, degrees_target):
    # Choose a new picture and set the prompt message.
    rand_int = random.randint(0, len(_UNICODE_PICTURES) - 1)
    picture = _UNICODE_PICTURES[rand_int]
    self.ui.SetHTML(_MSG_PROMPT_ROTATE_TABLET, id=_ID_PROMPT)

    degrees_previous = None
    while True:
      # Get current rotation.
      degrees_current = self._GetCurrentDegrees()

      # TODO(kitching): Research disabling ChromeOS screen rotation when in
      # factory mode.
      #
      # When the device is physically rotated, ChromeOS rotates the screen
      # accordingly.  If this wasn't the case, we could simply paint the
      # picture in the desired orientation, and have the operator rotate the
      # device appropriately:
      #
      #     | > |     | ^ |     | < |
      #
      # But, because ChromeOS automatically rotates the screen, if we keep the
      # picture's orientation the same, it would *always* face the same
      # direction, regardless of how the tablet is rotated.  (This makes
      # perfect sense.  We always want the UI to face the user in the correct
      # orientation.)  The picture would look like this:
      #
      #     | > |     | > |     | > |
      #
      # Thus, instructing the operator to align the picture to an upright
      # position becomes a fruitless effort.  So, we need to offset this
      # change by also rotating our picture every time the screen is rotated.
      # We set the rotation via CSS using degrees_delta as the angle.
      degrees_delta = degrees_target - degrees_current
      success = (degrees_delta == 0)

      # Check accelerometer if necessary.
      if (success and
          self.accel_controller and
          degrees_target in self.args.degrees_to_orientations):
        orientations = self.args.degrees_to_orientations[degrees_target]
        cal_data = self.accel_controller.GetCalibratedDataAverage(
            sample_rate=self.args.sample_rate_hz)
        if not self.accel_controller.IsWithinOffsetRange(
            cal_data, orientations, self.args.spec_ideal_values,
            self.args.spec_offset):
          success = False

      # Are we currently at our target?
      if success:
        return True
      # If the device has been rotated, we also need to update our picture's
      # orientation accordingly (see comment above describing degrees_delta).
      elif degrees_previous != degrees_current:
        self.ui.SetHTML(_HTML_BUILD_PICTURE(degrees_delta, picture),
                        id=_ID_PICTURE)

      # Target has still not been reached.  Sleep and continue.
      degrees_previous = degrees_current
      time.sleep(_POLL_ROTATION_INTERVAL)

  def _GetCurrentDegrees(self):
    display_info = None
    try:
      display_info = self.state.DeviceGetDisplayInfo()
    except Exception:
      pass
    if not display_info:
      raise Exception('Failed to get display_info')

    display_info = [info for info in display_info if info['isPrimary']]
    if len(display_info) != 1:
      raise Exception('Failed to get internal display')

    return display_info[0]['rotation']

  def runTest(self):
    self.ui.Run()
