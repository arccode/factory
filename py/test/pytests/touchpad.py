# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the functionality of touchpad.

Description
-----------
A touchpad test for touching, clicking, and multi-contact.

Test Procedure
--------------
1. Take off all your fingers from the touchpad.
2. Press spacebar to start.
3. Touch all `x_segments` * `y_segments` areas of touchpad with one finger.
   The corresponding regions in screen will become green once you touch them.
4. Scroll up and down with two fingers to make all cells in the right side of
   screen green.
5. Click left-top, right-top, left-bottom, and right-bottom corner of touchpad
   with one finger for `number_to_quadrant` times.
6. Click anywhere of touchpad with one finger until you have already done that
   `number_to_click` times.
7. Click anywhere of touchpad with two fingers for `number_to_click` times.

If you don't pass the test in `timeout_secs` seconds, the test will fail.

Dependency
----------
- Based on Linux evdev.

Examples
--------
To test touchpad with default parameters, add this in test list::

  {
    "pytest_name": "touchpad"
  }

If you want to change the time limit to 100 seconds::

  {
    "pytest_name": "touchpad",
    "args": {
      "timeout_secs": 100
    }
  }
"""

import logging

from cros.factory.external import evdev
from cros.factory.test import session
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import evdev_utils
from cros.factory.test.utils import touch_monitor
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class TouchpadMonitor(touch_monitor.MultiTouchMonitor):

  def __init__(self, device, test):
    super(TouchpadMonitor, self).__init__(device)
    self.test = test

  def OnKey(self, key_event_code):
    """See TouchMonitorBase.OnKey."""
    state = self.GetState()
    key_event_value = state.keys[key_event_code]
    if key_event_code == evdev.ecodes.BTN_LEFT and state.num_fingers == 1:
      self.test.OnSingleClick(key_event_value)
    else:
      if self.test.touchpad_has_right_btn:
        if key_event_code != evdev.ecodes.BTN_RIGHT:
          return
      else:
        if key_event_code != evdev.ecodes.BTN_LEFT or state.num_fingers != 2:
          return
      self.test.OnDoubleClick(key_event_value)

  def OnNew(self, slot_id):
    """See MultiTouchMonitor.OnNew."""
    state = self.GetState()
    if state.num_fingers <= 2:
      self.OnMove(slot_id)
    elif not self.test.already_alerted:
      self.test.already_alerted = True
      msg = 'number_fingers = %d' % state.num_fingers
      logging.error(msg)
      session.console.error(msg)
      self.test.ui.Alert(_(
          "Please don't put your third finger on the touchpad.\n"
          "If you didn't do that,\n"
          "treat this touch panel as a problematic one!!"))
      self.test.FailWithMessage()

  def OnMove(self, slot_id):
    """See MultiTouchMonitor.OnMove."""
    state = self.GetState()
    slot = state.slots[slot_id]
    self.test.OnMoveEvent(slot.x, slot.y, state.num_fingers)


class Quadrant:
  """The class is to update quadrant information.

  Update quadrant information according to x_ratio and y_ratio:

    Quadrant 1 is Right-Top Corner
    Quadrant 2 is Left-Top Corner
    Quadrant 3 is Left-Bottom Corner
    Quadrant 4 is Right-Bottom Corner
  """

  def __init__(self):
    self.quadrant = 0

  def UpdateQuadrant(self, x_ratio, y_ratio):
    if y_ratio < 0.5 <= x_ratio:
      self.quadrant = 1
    elif x_ratio < 0.5 and y_ratio < 0.5:
      self.quadrant = 2
    elif x_ratio < 0.5 <= y_ratio:
      self.quadrant = 3
    elif x_ratio >= 0.5 and y_ratio >= 0.5:
      self.quadrant = 4


class TouchpadTest(test_case.TestCase):
  """Tests the function of touchpad.

  The test checks the following function:
    1. Detect finger on every sector of touchpad.
    2. Two finger scrolling.
    3. Single click.
    4. Either double click or right click.

  Properties:
    self.touchpad_device_name: This can be probed from evdev.
    self.touchpad_has_right_btn: for touchpad with right button, we don't want
        to process double click. We will only process right_btn and left_btn.
    self.quadrant: This represents the current quadrant of mouse.
  """
  ARGS = [
      Arg('device_filter', (int, str),
          'Touchpad input event id or evdev name. The test will probe'
          ' for event id if it is not given.', default=None),
      Arg('timeout_secs', int, 'Timeout for the test.', default=20),
      Arg('number_to_click', int, 'Target number to click.', default=10),
      Arg('number_to_quadrant', int,
          'Target number to click for each quadrant.', default=3),
      Arg('x_segments', int, 'Number of X axis segments to test.', default=5),
      Arg('y_segments', int, 'Number of Y axis segments to test.', default=5)]

  def setUp(self):
    # Initialize properties
    self.touchpad_device_name = None
    self.touchpad_has_right_btn = False
    self.quadrant = Quadrant()
    self.touchpad_device = evdev_utils.FindDevice(self.args.device_filter,
                                                  evdev_utils.IsTouchpadDevice)
    self.monitor = None
    self.dispatcher = None
    self.already_alerted = False
    self.frontend_proxy = None

    self.x_segments = self.args.x_segments
    self.y_segments = self.args.y_segments

    self.scroll_tested = [False] * self.y_segments
    self.touch_tested = [[False] * self.y_segments
                         for unused_i in range(self.x_segments)]
    # Quadrant has index 1 to 4.
    self.quadrant_count = [None, 0, 0, 0, 0]
    self.single_click_count = 0
    self.double_click_count = 0
    # Disable lid function since lid open|close will trigger button up event.
    process_utils.CheckOutput(['ectool', 'forcelidopen', '1'])

  def tearDown(self):
    """Clean-up stuff.

    Terminates the running process or we'll have trouble stopping the
    test.
    """
    if self.dispatcher is not None:
      self.dispatcher.close()
    self.touchpad_device.ungrab()
    # Enable lid function.
    process_utils.CheckOutput(['ectool', 'forcelidopen', '0'])

  def GetSpec(self):
    """Gets device name, btn_right."""
    self.touchpad_device_name = self.touchpad_device.name
    if evdev.ecodes.BTN_RIGHT in self.monitor.GetState().keys:
      self.touchpad_has_right_btn = True
    logging.info('get device %s spec right_btn = %s',
                 self.touchpad_device_name, self.touchpad_has_right_btn)

  def OnMoveEvent(self, x, y, num_fingers):
    """Marks a scroll sector as tested or a move sector as tested."""
    self.quadrant.UpdateQuadrant(x, y)
    if num_fingers == 2:
      self.MarkScrollSectorTested(y)
    else:
      self.MarkSectorTested(x, y)

    self.CheckTestPassed()

  def OnSingleClick(self, down):
    """Draws single click event by calling javascript function.

    Args:
      down: bool
    """
    if not down:
      quadrant = self.quadrant.quadrant
      logging.info('mark single click up quadrant = %d', quadrant)
      self.frontend_proxy.MarkCircleTested('left')

      if self.single_click_count < self.args.number_to_click:
        self.single_click_count += 1
        self.frontend_proxy.UpdateCircleCountText(self.single_click_count,
                                                  self.double_click_count)

      if self.quadrant_count[quadrant] < self.args.number_to_quadrant:
        self.quadrant_count[quadrant] += 1
        self.frontend_proxy.UpdateQuadrantCountText(
            quadrant, self.quadrant_count[quadrant])
        if self.quadrant_count[quadrant] == self.args.number_to_quadrant:
          self.frontend_proxy.MarkQuadrantSectorTested(quadrant)
    else:
      logging.info('mark single click down')
      self.frontend_proxy.MarkCircleDown('left')

    self.CheckTestPassed()

  def OnDoubleClick(self, down):
    """Draws double click event by calling javascript function.

    Args:
      down: bool
    """
    if not down:
      logging.info('mark double click up')
      self.frontend_proxy.MarkCircleTested('right')

      if self.double_click_count < self.args.number_to_click:
        self.double_click_count += 1
        self.frontend_proxy.UpdateCircleCountText(self.single_click_count,
                                                  self.double_click_count)
    else:
      logging.info('mark double click down')
      self.frontend_proxy.MarkCircleDown('right')

    self.CheckTestPassed()

  def MarkScrollSectorTested(self, y_ratio):
    """Marks a scroll sector tested.

    Gets the scroll sector from y_ratio then calls Javascript to mark the sector
    as tested.
    """
    y_segment = int(y_ratio * self.y_segments)
    if 0 <= y_segment < self.y_segments:
      logging.debug('mark %d scroll segment tested', y_segment)
      self.scroll_tested[y_segment] = True
      self.frontend_proxy.MarkScrollSectorTested(y_segment)

  def MarkSectorTested(self, x_ratio, y_ratio):
    """Marks a touch sector tested.

    Gets the segment from x_ratio and y_ratio then calls Javascript to
    mark the sector as tested.
    """
    x_segment = int(x_ratio * self.x_segments)
    y_segment = int(y_ratio * self.y_segments)
    if 0 <= x_segment < self.x_segments and 0 <= y_segment < self.y_segments:
      logging.debug('mark x-%d y-%d sector tested', x_segment, y_segment)
      self.touch_tested[x_segment][y_segment] = True
      self.frontend_proxy.MarkSectorTested(x_segment, y_segment)

  def CheckTestPassed(self):
    """Check if all items have been tested."""
    if (self.single_click_count >= self.args.number_to_click and
        self.double_click_count >= self.args.number_to_click and
        min(self.quadrant_count[1:]) >= self.args.number_to_quadrant and
        all(self.scroll_tested) and all(all(r) for r in self.touch_tested)):
      self.PassTask()

  def FailWithMessage(self):
    """Fail the test with untested items."""
    fail_items = []

    for x, row in enumerate(self.touch_tested):
      fail_items.extend('touch-x-%d-y-%d' % (x, y)
                        for y, tested in enumerate(row) if not tested)

    fail_items.extend('scroll-y-%d' % y
                      for y, tested in enumerate(self.scroll_tested)
                      if not tested)

    fail_items.extend('quadrant-%d' % i
                      for i, c in enumerate(self.quadrant_count[1:], 1)
                      if c < self.args.number_to_quadrant)

    if self.single_click_count < self.args.number_to_click:
      fail_items.append('left click count: %d' % self.single_click_count)

    if self.double_click_count < self.args.number_to_click:
      fail_items.append('right click count: %d' % self.double_click_count)

    self.FailTask(
        'Touchpad test failed. Malfunction sectors: %s' % ', '.join(fail_items))

  def runTest(self):
    """Start the test if the touchpad is clear.

    This function ask operator to press SPACE key and run the test. It will
    first check whether the touchpad is clear or not. If not, it will notice
    the operator and fail the test. Else, it will clear the event buffer and
    start the test.
    """
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
    self.ui.HideElement('prompt')

    self.ui.StartCountdownTimer(self.args.timeout_secs, self.FailWithMessage)

    self.touchpad_device = evdev_utils.DeviceReopen(self.touchpad_device)
    self.touchpad_device.grab()
    self.monitor = TouchpadMonitor(self.touchpad_device, self)
    if self.monitor.GetState().num_fingers != 0:
      logging.error('Ghost finger detected.')
      self.ui.Alert(_(
          'Ghost finger detected!!\n'
          'Please treat this touch panel as a problematic one!!'))
      self.FailTask('Ghost finger detected.')

    self.frontend_proxy = self.ui.InitJSTestObject(
        'TouchpadTest', self.x_segments, self.y_segments,
        self.args.number_to_click, self.args.number_to_quadrant)

    self.GetSpec()
    self.dispatcher = evdev_utils.InputDeviceDispatcher(
        self.touchpad_device,
        self.event_loop.CatchException(self.monitor.Handler))
    logging.info('start monitor daemon thread')
    self.dispatcher.StartDaemon()

    self.WaitTaskEnd()
