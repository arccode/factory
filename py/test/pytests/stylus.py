# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test stylus functionality.

Description
-----------
Verifies if stylus is functional by asking operator to draw specified lines or
shapes using stylus.

For EMR stylus, drawing a diagonal line from left-bottom to right-top corner
should be sufficient to validate all scan lines. But for clamshells with hall
sensor, the magnet may cause EMR stylus to be non-functional in particular area.
To test that, set argument `endpoints_ratio` to build the lines for operator to
draw.

Test Procedure
--------------
1. When started, a diagonal line is displayed on screen.
2. Operator must use stylus to draw and follow the displayed line.
3. If the stylus moved too far (specified in argument `error_margin`) from the
   requested path, test will fail.

Dependency
----------
- Based on Linux evdev.

Examples
--------
To check stylus functionality by drawing a diagonal line, add this in test
list::

  {
    "pytest_name": "stylus"
  }

To check if the magnet in left side will cause problems, add this in test list
to draw a line from left-top to left-bottom::

  {
    "pytest_name": "stylus",
    "args": {
      "endpoints_ratio": [
        [0, 0],
        [0, 1]
      ]
    }
  }
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.external import evdev
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import evdev_utils
from cros.factory.test.utils import touch_monitor
from cros.factory.utils.arg_utils import Arg

_ID_CANVAS = 'stylus-test-canvas'

_HTML = '<canvas id="%s" style="display: none"></canvas>' % _ID_CANVAS

_MSG_PROMPT_CSS_CLASS = 'stylus-test-css-class'
_MSG_PROMPT_CSS = '.%s { font-size: 2em; }' % _MSG_PROMPT_CSS_CLASS
_MSG_PROMPT = i18n_test_ui.MakeI18nLabelWithClass(
    'Please extend the green line with stylus to the other end.<br>'
    'Stay between the two red lines.<br>'
    'Press SPACE to start; Esc to fail.', _MSG_PROMPT_CSS_CLASS)


class StylusMonitor(touch_monitor.SingleTouchMonitor):

  def __init__(self, device, ui):
    super(StylusMonitor, self).__init__(device)
    self._ui = ui

  def OnMove(self):
    """See SingleTouchMonitor.OnMove."""
    state = self.GetState()
    if state.keys[evdev.ecodes.BTN_TOUCH]:
      self._ui.CallJSFunction('handler', state.x, state.y)


class StylusTest(unittest.TestCase):
  """Stylus factory test."""

  ARGS = [
      Arg('device_filter', (int, str), 'Stylus input event id or evdev name.',
          default=None),
      Arg('error_margin', int,
          'Maximum tolerable distance to the diagonal line (in pixel).',
          default=25),
      Arg('begin_ratio', float,
          'The beginning position of the diagonal line segment to check. '
          'Should be in (0, 1).',
          default=0.01),
      Arg('end_ratio', float,
          'The ending position of the diagonal line segment to check. '
          'Should be in (0, 1).',
          default=0.99),
      Arg('step_ratio', float,
          'If the distance between an input event to the latest accepted '
          'input event is larger than this size, it would be ignored. '
          'Should be in (0, 1).',
          default=0.01),
      Arg('endpoints_ratio', list,
          'A list of two pairs, each pair contains the X and Y coordinates '
          'ratio of an endpoint of the line segment for operator to draw. '
          'Both endpoints must be on the border '
          '(e.g., X=0 or X=1 or Y=0 or Y=1).',
          default=[(0, 1), (1, 0)]),
      Arg('autostart', bool,
          'Starts the test automatically without prompting.  Operators can '
          'still press ESC to fail the test.',
          default=False),
      ]

  def setUp(self):
    self._device = evdev_utils.FindDevice(self.args.device_filter,
                                          evdev_utils.IsStylusDevice)
    self._monitor = None
    self._dispatcher = None

    assert self.args.error_margin >= 0
    assert 0 < self.args.begin_ratio < self.args.end_ratio < 1
    assert 0 < self.args.step_ratio < 1

    assert len(self.args.endpoints_ratio) == 2
    assert self.args.endpoints_ratio[0] != self.args.endpoints_ratio[1]
    for point in self.args.endpoints_ratio:
      assert isinstance(point, list) and len(point) == 2
      assert all(0 <= x_or_y <= 1 for x_or_y in point)
      assert point[0] in [0, 1] or point[1] in [0, 1]

    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._ui.AppendCSS(_MSG_PROMPT_CSS)
    self._template.SetState(_MSG_PROMPT)

  def _StartTest(self, event):
    del event  # Unused.

    self._ui.SetHTML(_HTML)
    self._ui.CallJSFunction('setupStylusTest',
                            _ID_CANVAS,
                            self.args.error_margin,
                            self.args.begin_ratio,
                            self.args.end_ratio,
                            self.args.step_ratio,
                            self.args.endpoints_ratio)
    self._device = evdev_utils.DeviceReopen(self._device)
    self._device.grab()
    self._monitor = StylusMonitor(self._device, self._ui)
    self._dispatcher = evdev_utils.InputDeviceDispatcher(self._device,
                                                         self._monitor.Handler)
    self._dispatcher.StartDaemon()

  def tearDown(self):
    if self._dispatcher is not None:
      self._dispatcher.close()
    self._device.ungrab()

  def runTest(self):
    self._ui.BindKeyJS(test_ui.ESCAPE_KEY, 'failTest();')
    if self.args.autostart:
      self._StartTest(None)
    else:
      self._ui.BindKey(test_ui.SPACE_KEY, self._StartTest)
    self._ui.Run()
