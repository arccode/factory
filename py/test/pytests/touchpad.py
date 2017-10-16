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
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.external import evdev
from cros.factory.test import countdown_timer
from cros.factory.test import session
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import evdev_utils
from cros.factory.test.utils import touch_monitor
from cros.factory.utils.arg_utils import Arg


_ID_COUNTDOWN_TIMER = 'touchpad-test-timer'

# The countdown timer will set the innerHTML later, so we should put some text
# here to make the layout consistent.
_HTML_TIMER = '<div id="%s">&nbsp;</div>' % _ID_COUNTDOWN_TIMER

_HTML_PROMPT = i18n_test_ui.MakeI18nLabelWithClass(
    'Please take off your fingers and then press SPACE to start testing...',
    'touchpad-test-prompt') + _HTML_TIMER


class TouchpadMonitor(touch_monitor.MultiTouchMonitor):

  def __init__(self, device, test):
    super(TouchpadMonitor, self).__init__(device)
    self.test = test

  def OnKey(self, key_event_code):
    """See TouchMonitorBase.OnKey."""
    state = self.GetState()
    key_event_value = state.keys[key_event_code]
    if key_event_code == evdev.ecodes.BTN_LEFT and state.num_fingers == 1:
      self.test.DrawSingleClick(key_event_value)
    else:
      if self.test.touchpad_has_right_btn:
        if key_event_code != evdev.ecodes.BTN_RIGHT:
          return
      else:
        if key_event_code != evdev.ecodes.BTN_LEFT or state.num_fingers != 2:
          return
      self.test.DrawDoubleClick(key_event_value)

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
      self.test.ui.CallJSFunction('failTest')

  def OnMove(self, slot_id):
    """See MultiTouchMonitor.OnMove."""
    state = self.GetState()
    slot = state.slots[slot_id]
    self.test.DrawMoveEvent(slot.x, slot.y, state.num_fingers)


class Quadrant(object):
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
    if x_ratio >= 0.5 and y_ratio < 0.5:
      self.quadrant = 1
    elif x_ratio < 0.5 and y_ratio < 0.5:
      self.quadrant = 2
    elif x_ratio < 0.5 and y_ratio >= 0.5:
      self.quadrant = 3
    elif x_ratio >= 0.5 and y_ratio >= 0.5:
      self.quadrant = 4


class TouchpadTest(unittest.TestCase):
  """Tests the function of touchpad.

  The test checks the following function:
    1. Detect finger on every sector of touchpad.
    2. Two finger scrolling.
    3. Single click.
    4. Either double click or right click.

  Properties:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.touchpad_device_name: This can be probed from evdev.
    self.touchpad_has_right_btn: for touchpad with right button, we don't want
        to process double click. We will only process right_btn and left_btn.
    self.quadrant: This represents the current quadrant of mouse.
  """
  ARGS = [
      Arg('device_filter', (int, str),
          'Touchpad input event id or evdev name. The test will probe'
          ' for event id if it is not given.', default=None, optional=True),
      Arg('timeout_secs', int, 'Timeout for the test.', default=20),
      Arg('number_to_click', int, 'Target number to click.', default=10),
      Arg('number_to_quadrant', int,
          'Target number to click for each quadrant.', default=3),
      Arg('x_segments', int, 'Number of X axis segments to test.', default=5),
      Arg('y_segments', int, 'Number of Y axis segments to test.', default=5)]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSSLink('touchpad.css')
    self.template.SetState(_HTML_PROMPT)

    # Initialize properties
    self.touchpad_device_name = None
    self.touchpad_has_right_btn = False
    self.quadrant = Quadrant()
    self.touchpad_device = evdev_utils.FindDevice(self.args.device_filter,
                                                  evdev_utils.IsTouchpadDevice)
    self.monitor = None
    self.dispatcher = None
    self.already_alerted = False

    logging.info('start countdown timer daemon thread')
    countdown_timer.StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.CallJSFunction('failTest'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

  def tearDown(self):
    """Clean-up stuff.

    Terminates the running process or we'll have trouble stopping the
    test.
    """
    if self.dispatcher is not None:
      self.dispatcher.close()
    self.touchpad_device.ungrab()

  def GetSpec(self):
    """Gets device name, btn_right."""
    self.touchpad_device_name = self.touchpad_device.name
    if evdev.ecodes.BTN_RIGHT in self.monitor.GetState().keys:
      self.touchpad_has_right_btn = True
    logging.info('get device %s spec right_btn = %s',
                 self.touchpad_device_name, self.touchpad_has_right_btn)

  def DrawMoveEvent(self, x, y, num_fingers):
    """Marks a scroll sector as tested or a move sector as tested."""
    self.quadrant.UpdateQuadrant(x, y)
    if num_fingers == 2:
      self.MarkScrollSectorTested(y)
    else:
      self.MarkSectorTested(x, y)

  def DrawSingleClick(self, down):
    """Draws single click event by calling javascript function.

    Args:
      down: bool
    """
    if not down:
      logging.info('mark single click up')
      self.ui.CallJSFunction('markSingleClickUp', self.quadrant.quadrant)
    else:
      logging.info('mark single click down')
      self.ui.CallJSFunction('markSingleClickDown', self.quadrant.quadrant)

  def DrawDoubleClick(self, down):
    """Draws double click event by calling javascript function.

    Args:
      down: bool
    """
    if not down:
      logging.info('mark double click up')
      self.ui.CallJSFunction('markDoubleClickUp')
    else:
      logging.info('mark double click down')
      self.ui.CallJSFunction('markDoubleClickDown')

  def MarkScrollSectorTested(self, y_ratio):
    """Marks a scroll sector tested.

    Gets the scroll sector from y_ratio then calls Javascript to mark the sector
    as tested.
    """
    y_segment = int(y_ratio * self.args.y_segments)
    logging.debug('mark %d scroll segment tested', y_segment)
    self.ui.CallJSFunction('markScrollSectorTested', y_segment)

  def MarkSectorTested(self, x_ratio, y_ratio):
    """Marks a touch sector tested.

    Gets the segment from x_ratio and y_ratio then calls Javascript to
    mark the sector as tested.
    """
    x_segment = int(x_ratio * self.args.x_segments)
    y_segment = int(y_ratio * self.args.y_segments)
    logging.debug('mark x-%d y-%d sector tested', x_segment, y_segment)
    self.ui.CallJSFunction('markSectorTested', x_segment, y_segment)

  def StartTest(self, event):
    """Start the test if the touchpad is clear.

    This function is invoked when SPACE key is pressed. It will first check
    whether the touchpad is clear or not. If not, it will notice the operator
    and fail the test. Else, it will clear the event buffer and start the test.

    Args:
      event: a BindKey event object, not used.
    """
    del event  # Unused.

    self.touchpad_device = evdev_utils.DeviceReopen(self.touchpad_device)
    self.touchpad_device.grab()
    self.monitor = TouchpadMonitor(self.touchpad_device, self)
    if self.monitor.GetState().num_fingers != 0:
      logging.error('Ghost finger detected.')
      self.ui.Alert(_(
          'Ghost finger detected!!\n'
          'Please treat this touch panel as a problematic one!!'))
      self.ui.Fail('Ghost finger detected.')
      return

    self.template.SetState(_HTML_TIMER)
    self.ui.CallJSFunction('setupTouchpadTest', self.args.x_segments,
                           self.args.y_segments, self.args.number_to_click,
                           self.args.number_to_quadrant)

    self.GetSpec()
    self.dispatcher = evdev_utils.InputDeviceDispatcher(self.touchpad_device,
                                                        self.monitor.Handler)
    logging.info('start monitor daemon thread')
    self.dispatcher.StartDaemon()

  def runTest(self):
    self.ui.BindKey(test_ui.SPACE_KEY, self.StartTest, once=True)
    self.ui.Run()
