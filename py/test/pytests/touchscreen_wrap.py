# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests touchscreen by drawing a warp-in pattern.

In this test, we split the screen in C x R blocks. We ask operators to
draw blocks in sequence. Right now the drawing pattern is:

1. Starting from upper-left block, move to rightmost block.
2. Then move down, left, up, to draw a outer retangular circle.
3. Move to the inner upper-left block (1, 1), repeat 1-2.
4. Until the center block is reached.

The index of block (x, y) is defined as::

  index =  x + y * xSegment (number of blocks in x-axis).

For, example, a 3x3 grid::

  0 1 2
  3 4 5
  6 7 8

The drawing sequence is: 0, 1, 2, 5, 8, 7, 6, 3, 4.

It uses Chrome event API or evdev to get touch events.
Test logic is in touchscreen.js.
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.external.evdev import ecodes  # pylint: disable=E0611
from cros.factory.test import test_ui
from cros.factory.test.utils import evdev_utils
from cros.factory.test.utils import touch_monitor
from cros.factory.utils.arg_utils import Arg


_ID_CONTAINER = 'touchscreen-test-container'

# The style is in touchscreen_wrap.css.
# The layout contains one div for touchscreen.
_HTML_TOUCHSCREEN = (
    '<link rel="stylesheet" type="text/css" href="touchscreen_wrap.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)


class StylusMonitor(touch_monitor.SingleTouchMonitor):
  """Stylus monitor."""

  def __init__(self, device, ui, code):
    """Initialize.

    Args:
      device: evdev.InputDevice
      ui: test_ui.UI
      code: Which key to monitor: BTN_TOUCH (for touching) or BTN_TOOL_PEN
        (for hovering).
    """
    super(StylusMonitor, self).__init__(device)
    self._ui = ui
    self._code = code
    # A boolean flag indicating if BTN_TOUCH or BTN_TOOL_PEN is on.
    self._flag = self._state.keys[code]

  def _EmitEvent(self, receiver):
    state = self.GetState()
    self._ui.CallJSFunction('goofyTouchListener', receiver, state.x, state.y)

  def OnKey(self, code):
    """Called by Handler after state of a key changed."""
    if code == self._code:
      self._flag = not self._flag
      if self._flag:
        self._EmitEvent('touchStartHandler')
      else:
        self._EmitEvent('touchEndHandler')

  def OnMove(self):
    """Called by Handler after X or Y coordinate changes."""
    if self._flag:
      self._EmitEvent('touchMoveHandler')


class TouchscreenMonitor(touch_monitor.MultiTouchMonitor):
  """Touchscreen monitor."""

  def __init__(self, device, ui):
    """Initialize.

    Args:
      device: evdev.InputDevice
      ui: test_ui.UI
    """
    super(TouchscreenMonitor, self).__init__(device)
    self._ui = ui

  def _EmitEvent(self, receiver, slot_id):
    slot = self.GetState().slots[slot_id]
    self._ui.CallJSFunction('goofyTouchListener', receiver, slot.x, slot.y)

  def OnNew(self, slot_id):
    """Called by Handler after a new contact comes."""
    self._EmitEvent('touchStartHandler', slot_id)

  def OnMove(self, slot_id):
    """Called by Handler after a contact moved."""
    self._EmitEvent('touchMoveHandler', slot_id)

  def OnLeave(self, slot_id):
    """Called by Handler after a contact leaves."""
    self._EmitEvent('touchEndHandler', slot_id)


class TouchscreenTest(unittest.TestCase):
  """Tests touchscreen by drawing blocks in sequence.

  Properties:
    self._device: evdev.InputDevice
    self._dispatcher: evdev_utils.InputDeviceDispatcher
    self._monitor: StylusMonitor or TouchscreenMonitor
    self._ui: test_ui.UI
  """
  ARGS = [
      Arg('x_segments', int, 'Number of segments in x-axis.', default=5),
      Arg('y_segments', int, 'Number of segments in y-axis.', default=5),
      Arg('retries', int, 'Number of retries.', default=5),
      Arg('demo_interval_ms', int,
          'Interval (ms) to show drawing pattern. <= 0 means no demo.',
          default=150),
      Arg('stylus', bool, 'Testing stylus or not.', default=False),
      Arg('e2e_mode', bool,
          'Perform end-to-end test or not (for touchscreen).',
          default=False),
      Arg('event_id', int, 'Evdev input event id.', optional=True),
      Arg('hover_mode', bool, 'Test hovering or touching (for stylus).',
          default=False),
      ]

  def setUp(self):
    if self.args.stylus:
      self._device = evdev_utils.FindDevice(self.args.event_id,
                                            evdev_utils.IsStylusDevice)
    else:
      if self.args.e2e_mode:
        self._device = None
      else:
        self._device = evdev_utils.FindDevice(self.args.event_id,
                                              evdev_utils.IsTouchscreenDevice)
    self._dispatcher = None
    self._monitor = None

    # Initialize frontend presentation.
    self._ui = test_ui.UI()
    self._ui.AppendHTML(_HTML_TOUCHSCREEN)
    self._ui.CallJSFunction(
        'setupTouchscreenTest', _ID_CONTAINER, self.args.x_segments,
        self.args.y_segments, self.args.retries, self.args.demo_interval_ms,
        self.args.e2e_mode)

  def tearDown(self):
    if self._dispatcher is not None:
      self._dispatcher.close()
    if self._device is not None:
      self._device.ungrab()

  def OnFailPressed(self):
    """Fails the test."""
    self._ui.CallJSFunction('failTest')

  def runTest(self):
    if self._device is not None:
      self._device = evdev_utils.DeviceReopen(self._device)
      self._device.grab()
      if self.args.stylus:
        self._monitor = StylusMonitor(
            self._device, self._ui,
            ecodes.BTN_TOOL_PEN if self.args.hover_mode else ecodes.BTN_TOUCH)
      else:
        self._monitor = TouchscreenMonitor(self._device, self._ui)
      self._dispatcher = evdev_utils.InputDeviceDispatcher(
          self._device, self._monitor.Handler)
      self._dispatcher.StartDaemon()

    self._ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnFailPressed())
    self._ui.Run()
