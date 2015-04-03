# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests ChromeOS screen rotation.

Tests that ChromeOS properly rotates the screen when the device is physically
rotated in tablet mode.

Usage example::

    OperatorTest(
        id='TabletRotation',
        label_zh=u'平板电脑旋转测试',
        pytest_name='tablet_rotation',
        dargs={
            'timeout_secs': HOURS_24,
            'prompt_flip_tablet': False,
            'prompt_flip_notebook': True,
        })
"""

import random
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.pytests.tablet_mode_ui import TabletModeUI
from cros.factory.test.ui_templates import OneSection


_DEFAULT_TIMEOUT = 30
_UNICODE_PICTURES = u'☃☹☎'
_TEST_DEGREES = [90, 180, 270, 0]
_POLL_ROTATION_INTERVAL = 0.1

_MSG_PROMPT_ROTATE_TABLET = test_ui.MakeLabel(
    'Rotate the tablet to correctly align the picture.', u'TODO')

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
  ]

  def setUp(self):
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

    if self.args.prompt_flip_tablet:
      self.tablet_mode_ui.AskForTabletMode(
          lambda _: self.InitTestRotation())
    else:
      self.InitTestRotation()

  def InitTestRotation(self, degrees_targets=None, picture=None):
    if degrees_targets is None:
      degrees_targets = _TEST_DEGREES

    template = OneSection(self.ui)
    template.SetState(_HTML + _HTML_COUNTDOWN_TIMER)
    self.ui.AppendCSS(_CSS + _CSS_COUNTDOWN_TIMER)
    self._TestRotation(degrees_targets, picture)

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

  def _TestRotation(self, degrees_targets=None, picture=None):
    # Base case for recursion termination: all degrees_targets are tested.
    if not degrees_targets:
      self.ui.Pass()
      return

    # Choose a new picture!
    if not picture:
      rand_int = random.randint(0, len(_UNICODE_PICTURES) - 1)
      picture = _UNICODE_PICTURES[rand_int]

    # Get current rotation.
    try:
      degrees_current = self._GetCurrentDegrees()
    except Exception as e:
      self.ui.Fail(e.msg)
      return

    degrees_delta = degrees_targets[0] - degrees_current

    # Are we currently at our target?
    if degrees_delta == 0:
      self.tablet_mode_ui.FlashSuccess()
      # The test for degrees_targets[0] succeeded.  Continue testing
      # recursively.  Use InitTestRotation to reset the HTML template and CSS,
      # since they were reset by tablet_mode_ui.FlashSuccess.
      self.InitTestRotation(degrees_targets=degrees_targets[1:])
    else:
      self.ui.SetHTML(_MSG_PROMPT_ROTATE_TABLET, id=_ID_PROMPT)
      self.ui.SetHTML(_HTML_BUILD_PICTURE(degrees_delta, picture),
                      id=_ID_PICTURE)
      time.sleep(_POLL_ROTATION_INTERVAL)
      self._TestRotation(degrees_targets, picture)

  def runTest(self):
    self.ui.Run()
