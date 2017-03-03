# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.external import evdev
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg

_ID_CANVAS = 'stylus-test-canvas'

_HTML = '<canvas id="%s" style="display: none"></canvas>' % _ID_CANVAS

_MSG_PROMPT_CSS_CLASS = 'stylus-test-css-class'
_MSG_PROMPT_CSS = '.%s { font-size: 2em; }' % _MSG_PROMPT_CSS_CLASS
_MSG_PROMPT = i18n_test_ui.MakeI18nLabelWithClass(
    'Please draw a line with stylus from bottom left corner to top right '
    'corner. Stay between the two red lines.<br>'
    'Press SPACE to start; Esc to fail.', _MSG_PROMPT_CSS_CLASS)


class _AbsInfo(object):

  def __init__(self, absinfo):
    self.value = absinfo.value
    self.offset = absinfo.min
    self.range = float(absinfo.max - absinfo.min)

  def Update(self, value):
    self.value = value

  def GetNormalizedValue(self):
    return min(max(0.0, (self.value - self.offset) / self.range), 1.0)


class StylusTest(unittest.TestCase):
  """Stylus factory test."""

  ARGS = [
      Arg('stylus_event_id', int, 'Stylus input event id.', optional=True),
      Arg('error_margin', int,
          'Maximum tolerable distance to the diagonal line (in pixel).',
          default=25),
      Arg('begin_position', float,
          'The beginning position of the diagnoal line segment to check. '
          'Should be in (0, 1).',
          default=0.01),
      Arg('end_position', float,
          'The ending position of the diagnoal line segment to check. '
          'Should be in (0, 1).',
          default=0.99),
      Arg('step_size', float,
          'If the distance between an input event to the latest accepted '
          'input event is larger than this size, it would be ignored. '
          'Should be in (0, 1).',
          default=0.01)]

  def setUp(self):
    self._device = evdev_utils.FindDevice(self.args.stylus_event_id,
                                          evdev_utils.IsStylusDevice)
    abscaps = {
        pair[0]: pair[1]
        for pair in self._device.capabilities()[evdev.ecodes.EV_ABS]}
    self._x = _AbsInfo(abscaps[evdev.ecodes.ABS_X])
    self._y = _AbsInfo(abscaps[evdev.ecodes.ABS_Y])
    self._touch = False
    self._dispatcher = None

    assert self.args.error_margin >= 0
    assert 0 < self.args.begin_position < self.args.end_position < 1
    assert 0 < self.args.step_size < 1

    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._ui.AppendCSS(_MSG_PROMPT_CSS)
    self._template.SetState(_MSG_PROMPT)

  def _Handler(self, event):
    if event.type == evdev.ecodes.EV_ABS:
      if event.code == evdev.ecodes.ABS_X:
        self._x.Update(event.value)
      elif event.code == evdev.ecodes.ABS_Y:
        self._y.Update(event.value)
    elif event.type == evdev.ecodes.EV_KEY:
      if event.code == evdev.ecodes.BTN_TOUCH:
        self._touch = event.value != 0
    elif event.type == evdev.ecodes.EV_SYN:
      if self._touch:
        self._ui.CallJSFunction(
            'handler',
            self._x.GetNormalizedValue(),
            self._y.GetNormalizedValue())

  def _StartTest(self, _):
    self._ui.SetHTML(_HTML)
    self._ui.CallJSFunction('setupStylusTest',
                            _ID_CANVAS,
                            self.args.error_margin,
                            self.args.begin_position,
                            self.args.end_position,
                            self.args.step_size)
    self._ui.CallJSFunction('startTest')
    self._dispatcher = evdev_utils.InputDeviceDispatcher(self._device,
                                                         self._Handler)
    self._dispatcher.StartDaemon()

  def tearDown(self):
    if self._dispatcher is not None:
      self._dispatcher.close()

  def runTest(self):
    self._ui.BindKeyJS(test_ui.ESCAPE_KEY, 'failTest();')
    self._ui.BindKey(test_ui.SPACE_KEY, self._StartTest)
    self._ui.Run()
