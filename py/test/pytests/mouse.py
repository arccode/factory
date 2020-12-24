# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the functionality of a mouse/trackpoint.

Description
-----------
A mouse/trackpoint test for moving and clicking.

Test Procedure
--------------
1. Move the mouse in all 4 directions. The corresponding grid will become green
   once you move in that direction. The moving speed must be greater than
   `move_threshold` for the test to detect the moving direction of the mouse.
2. Click the left, middle and right button of the mouse. The corresponding grid
   will become green once you click the button.

If you don't pass the test in `timeout_secs` seconds, the test will fail.

Dependency
----------
- Based on Linux evdev.

Examples
--------
To test mouse/trackpoint with default parameters, add this in test list::

  {
    "pytest_name": "mouse"
  }

If you want to change the time limit to 100 seconds::

  {
    "pytest_name": "mouse",
    "args": {
      "timeout_secs": 100
    }
  }
"""

import logging
import time

from cros.factory.test import test_case
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

from cros.factory.external import evdev


class MouseTest(test_case.TestCase):
  """Tests the function of a mouse/trackpoint."""
  ARGS = [
      Arg('device_filter', (int, str),
          ('Mouse input event id or evdev name. The test will probe for '
           'event id if it is not given.'), default=None),
      Arg('timeout_secs', int, 'Timeout for thte test.', default=20),
      Arg('button_updown_secs', float,
          'Max duration between button up and down.', default=0.6),
      Arg('move_threshold', int, 'Speed threshold to detect the move direction',
          default=3)
  ]

  def setUp(self):
    self.assertGreater(self.args.move_threshold, 0,
                       'move_threshold must be greater than 0.')
    self.mouse_device = evdev_utils.FindDevice(
        self.args.device_filter, evdev_utils.IsMouseDevice)
    self.mouse_device_name = self.mouse_device.name

    self.frontend_proxy = None
    self.dispatcher = None
    self.down_keycode_time = {}

    self.move_tested = {
        'up': False,
        'down': False,
        'left': False,
        'right': False}
    self.click_tested = {
        'left': False,
        'middle': False,
        'right': False
    }
    # Disable lid function since lid open|close will trigger button up event.
    process_utils.CheckOutput(['ectool', 'forcelidopen', '1'])

  def tearDown(self):
    self.dispatcher.close()
    self.mouse_device.ungrab()
    # Enable lid function.
    process_utils.CheckOutput(['ectool', 'forcelidopen', '0'])

  def HandleEvent(self, event):
    """Handler for evdev events."""
    if event.type == evdev.ecodes.EV_KEY:
      self.OnClickButton(event.code, event.value)
    elif event.type == evdev.ecodes.EV_REL:
      self.OnMoveDirection(event.code, event.value)

  def OnClickButton(self, keycode, value):
    button_map = {
        evdev.ecodes.BTN_LEFT: 'left',
        evdev.ecodes.BTN_MIDDLE: 'middle',
        evdev.ecodes.BTN_RIGHT: 'right'
    }
    button = button_map[keycode]
    if value == 1:
      if self.down_keycode_time:
        self.FailTask('More than one button clicked')
      self.down_keycode_time[keycode] = time.time()
      self.frontend_proxy.MarkClickButtonDown(button)
    else:
      duration = time.time() - self.down_keycode_time[keycode]
      if duration > self.args.button_updown_secs:
        self.FailTask(
            'The time between button up and down is %f second(s), longer '
            'than %f second(s).' % (duration, self.args.button_updown_secs))
      del self.down_keycode_time[keycode]
      self.frontend_proxy.MarkClickButtonTested(button)
      self.click_tested[button] = True
      self.CheckTestPassed()

  def OnMoveDirection(self, keycode, value):
    if abs(value) < self.args.move_threshold:
      return
    if keycode == evdev.ecodes.REL_X:
      direction = 'right' if value > 0 else 'left'
    elif keycode == evdev.ecodes.REL_Y:
      direction = 'down' if value > 0 else 'up'
    else:
      logging.warning('Unknown keycode: %d', keycode)
      return

    self.frontend_proxy.MarkMoveDirectionTested(direction)
    self.move_tested[direction] = True
    self.CheckTestPassed()

  def CheckTestPassed(self):
    """Check if all items have been tested."""
    if all(self.click_tested.values()) and all(self.move_tested.values()):
      self.PassTask()

  def FailTestTimeout(self):
    """Fail the test due to timeout, and log untested functions."""
    failed_move = [
        direction for direction, tested in self.move_tested.items()
        if not tested]
    failed_click = [
        button for button, tested in self.click_tested.items() if not tested]
    self.FailTask('Test timed out. Malfunction move directions: %r. '
                  'Malfunction buttons: %r' % (failed_move, failed_click))

  def runTest(self):
    self.mouse_device.grab()

    self.ui.StartCountdownTimer(self.args.timeout_secs, self.FailTestTimeout)
    self.frontend_proxy = self.ui.InitJSTestObject('MouseTest')

    self.dispatcher = evdev_utils.InputDeviceDispatcher(
        self.mouse_device,
        self.event_loop.CatchException(self.HandleEvent))
    logging.info('start monitor daemon thread')
    self.dispatcher.StartDaemon()

    self.WaitTaskEnd()
