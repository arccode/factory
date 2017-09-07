# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests touchscreen or stylus by drawing in any order or in spiral pattern.

Description
-----------
In this test, screen area is segmented into `x_segments` x `y_segments` blocks.
If argument `spiral_mode` is True, the operator has to swipe the blocks in
clockwise spiral pattern. Otherwise the operator has to touch all the blocks in
arbitrary order.

In `spiral_mode`, the pattern is:

1. Starting from upper-left block, move to rightmost block.
2. Then move down, left, up, to draw a outer rectangular circle.
3. Move to the inner upper-left block (1, 1), repeat 1-2.
4. Until the center block is reached.

The index of block (x, y) is defined as::

  index =  x + y * x_segments (number of blocks in x-axis).

For, example, a 3x3 grid::

  0 1 2
  3 4 5
  6 7 8

The clockwise spiral drawing sequence is: 0, 1, 2, 5, 8, 7, 6, 3, 4.

There are two modes available: end-to-end mode and evdev mode.

- End-to-end mode uses Chrome touch event API.
- Evdev mode uses Linux evdev.

Test logic is in touchscreen.js.

Test Procedure
--------------
1. Once the test started, it would be set to fullscreen and shows
   `x_segments` x `y_segments` grey blocks.
2. Draw these blocks green by touching them (or move your stylus to make it
   hovering on a block in hover mode) in specified order. Test will pass after
   all blocks being green.
3. If there is any problem with the touch device, press Escape to abort and
   mark this test failed.
4. If `timeout_secs` is set and the test couldn't be passed in `timeout_secs`
   seconds, the test will fail automatically.

Dependency
----------
- End-to-end mode is based on Chrome touch event API.
- Non end-to-end mode is based on Linux evdev.

Examples
--------
To test touchscreen with 30x20 blocks::

  OperatorTest(pytest_name='touchscreen',
               dargs=dict(x_segments=20, y_segments=30))

To test touchscreen in end-to-end mode and cancel the time limit::

  OperatorTest(pytest_name='touchscreen',
               dargs=dict(e2e_mode=True, timeout_secs=None))

To test touchscreen without spiral order restriction::

  OperatorTest(pytest_name='touchscreen',
               dargs=dict(spiral_mode=False))

To test stylus in hover mode::

  OperatorTest(pytest_name='touchscreen',
               dargs=dict(stylus=True, hover_mode=True))
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.external.evdev import ecodes  # pylint: disable=E0611
from cros.factory.test import countdown_timer
from cros.factory.test import test_ui
from cros.factory.test.utils import evdev_utils
from cros.factory.test.utils import touch_monitor
from cros.factory.utils.arg_utils import Arg


_ID_CONTAINER = 'touchscreen-test-container'

# The style is in touchscreen.css.
# The layout contains one div for touchscreen.
_HTML_TOUCHSCREEN = (
    '<link rel="stylesheet" type="text/css" href="touchscreen.css">'
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
      Arg('retries', int, 'Number of retries (for spiral_mode).', default=5),
      Arg('demo_interval_ms', int,
          'Interval (ms) to show drawing pattern (for spiral mode). '
          '<= 0 means no demo.',
          default=150),
      Arg('stylus', bool, 'Testing stylus or not.', default=False),
      Arg('e2e_mode', bool,
          'Perform end-to-end test or not (for touchscreen).',
          default=False),
      Arg('spiral_mode', bool,
          'Do blocks need to be drawn in spiral order or not.',
          default=True),
      Arg('device_filter', (int, str), 'Evdev input event id or name.',
          optional=True),
      Arg('hover_mode', bool, 'Test hovering or touching (for stylus).',
          default=False),
      Arg('timeout_secs', (int, type(None)),
          'Timeout for the test. None for no time limit.', default=20),
      ]

  def setUp(self):
    if self.args.stylus:
      self._device = evdev_utils.FindDevice(self.args.device_filter,
                                            evdev_utils.IsStylusDevice)
    else:
      if self.args.e2e_mode:
        self._device = None
      else:
        self._device = evdev_utils.FindDevice(self.args.device_filter,
                                              evdev_utils.IsTouchscreenDevice)
    self._dispatcher = None
    self._monitor = None

    # Initialize frontend presentation.
    self._ui = test_ui.UI()
    self._ui.AppendHTML(_HTML_TOUCHSCREEN)
    self._ui.CallJSFunction(
        'setupTouchscreenTest', _ID_CONTAINER, self.args.x_segments,
        self.args.y_segments, self.args.retries, self.args.demo_interval_ms,
        self.args.e2e_mode, self.args.spiral_mode)

    if self.args.timeout_secs:
      countdown_timer.StartCountdownTimer(
          self.args.timeout_secs, self.OnFailPressed, self._ui,
          'touchscreen_countdown_timer')

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
