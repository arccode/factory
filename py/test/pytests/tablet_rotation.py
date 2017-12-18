# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests screen rotation through ChromeOS and accelerometer data.

Description
-----------
Tests that ChromeOS properly rotates the screen when the device is physically
rotated in tablet mode.

If ``check_accelerometer`` is set, also checks that the orientation matches up
with accelerometer data.

Test Procedure
--------------
1. A picture would be shown on the screen. Operator should rotate the tablet to
   align with the image. This would repeat four times with each orientations,
   and the test automatically pass when the desired orientation is reached.

2. If ``check_accelerometer`` is set, the test would also check if the value of
   accelerometer is within acceptable range for each orientation.

Dependency
----------
``chrome.display.system.getInfo`` in Chrome extension to get screen orientation.

If ``check_accelerometer`` is set, also depends on device API
``cros.factory.device.accelerometer``.

Examples
--------
To test screen rotation for Chrome, add this in test list::

  {
    "pytest_name": "tablet_rotation"
  }

To test screen rotation, and have a timeout of 10 minutes::

  {
    "pytest_name": "tablet_rotation",
    "args": {
      "timeout_secs": 600
    }
  }

To also check accelerometer when testing screen rotation::

  {
    "pytest_name": "tablet_rotation",
    "args": {
      "check_accelerometer": true,
      "degrees_to_orientations": [
        [
          0,
          {
            "in_accel_x": 0,
            "in_accel_y": 1,
            "in_accel_z": 0
          }
        ],
        [
          90,
          {
            "in_accel_x": 1,
            "in_accel_y": 0,
            "in_accel_z": 0
          }
        ],
        [
          180,
          {
            "in_accel_x": 0,
            "in_accel_y": -1,
            "in_accel_z": 0
          }
        ],
        [
          270,
          {
            "in_accel_x": -1,
            "in_accel_y": 0,
            "in_accel_z": 0
          }
        ]
      ],
      "spec_offset": [0.5, 0.5]
    }
  }

To test screen rotation for Chrome and prompt operator to flip before and after
the test::

  {
    "subtests": [
      {
        "pytest_name": "tablet_mode",
        "args": {
          "prompt_flip_tablet": true
        }
      },
      {
        "pytest_name": "tablet_rotation"
      },
      {
        "pytest_name": "tablet_mode",
        "args": {
          "prompt_flip_notebook": true
        }
      }
    ]
  }
"""

import random
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import countdown_timer
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.pytests import tablet_mode_ui
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_DEFAULT_TIMEOUT = 30
_UNICODE_PICTURES = u'☃☺☎'
_TEST_DEGREES = [90, 180, 270, 0]
_POLL_ROTATION_INTERVAL = 0.1

_MSG_PROMPT_ROTATE_TABLET = i18n_test_ui.MakeI18nLabel(
    'Rotate the tablet to correctly align the picture, holding it at an '
    'upright 90-degree angle.')

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
  font-size: 2em;
  align-self: flex-end;
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
          default=_DEFAULT_TIMEOUT),
      Arg('check_accelerometer', bool,
          'In addition to checking the ChromeOS screen orientation, also check '
          'accelerometer data to ensure it reports the same orientation.',
          default=False),
      Arg('accelerometer_location', str,
          'If check_accelerometer is true, the location of accelerometer that '
          'should be checked. Should be either "lid" or "base"',
          default='lid'),
      Arg('degrees_to_orientations', list,
          'A list of [key, value] pairs. '
          'Keys: degree of the orientation, limited to [0, 90, 180, 270]. '
          'Values: a dictionary containing orientation configuration.  Keys '
          'should be the name of the accelerometer signal. The possible keys '
          'are "in_accel_(x|y|z)". Values should be one of [0, 1, -1], '
          'representing the ideal value for gravity under such orientation.',
          default=[]),
      Arg('spec_offset', list,
          'Two numbers, ex: [1.5, 1.5] '
          'indicating the tolerance for the digital output of sensors under '
          'zero gravity and one gravity.', default=None),
      Arg('sample_rate_hz', int,
          'The sample rate in Hz to get raw data from '
          'accelerometers.', default=20),
  ]

  def setUp(self):
    # args.check_accelerometer implies the following required arguments:
    #   degrees_to_orientations
    #   spec_offset
    self.dut = device_utils.CreateDUTInterface()
    self.accel_controller = None
    if self.args.check_accelerometer:
      if not all([self.args.degrees_to_orientations,
                  self.args.spec_offset]):
        self.fail('If running in check_accelerometer mode, please provide '
                  'arguments degrees_to_orientations and spec_offset.')
        return

      self.accel_controller = self.dut.accelerometer.GetController(
          location=self.args.accelerometer_location)
      self.degrees_to_orientations = dict(self.args.degrees_to_orientations)

    self.ui = test_ui.UI()
    self.state = state.get_instance()
    self.tablet_mode_ui = tablet_mode_ui.TabletModeUI(self.ui,
                                                      _HTML_COUNTDOWN_TIMER,
                                                      _CSS_COUNTDOWN_TIMER)

  def TestRotationUIFlow(self, degrees_targets=None):
    if degrees_targets is None:
      degrees_targets = _TEST_DEGREES

    for degrees_target in degrees_targets:
      # Initialize UI template, HTML and CSS.
      template = ui_templates.OneSection(self.ui)
      template.SetState(_HTML + _HTML_COUNTDOWN_TIMER)
      self.ui.AppendCSS(_CSS + _CSS_COUNTDOWN_TIMER)

      self._PromptAndWaitForRotation(degrees_target)

      self.tablet_mode_ui.FlashSuccess()

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
          degrees_target in self.degrees_to_orientations):
        orientations = self.degrees_to_orientations[degrees_target]
        cal_data = self.accel_controller.GetData(
            sample_rate=self.args.sample_rate_hz)
        if not self.accel_controller.IsWithinOffsetRange(
            cal_data, orientations, self.args.spec_offset):
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
    # Create a thread to run countdown timer.
    countdown_timer.StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Tablet rotation test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

    self.ui.RunInBackground(self.TestRotationUIFlow)
    self.ui.Run()
