# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the functionality of touchscreen."""

import evdev
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import countdown_timer
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg


_ID_CONTAINER = 'touchscreen-test-container'

# The style is in touchscreen.css
# The layout contains one div for touchscreen.
_HTML_TOUCHSCREEN = (
    '<link rel="stylesheet" type="text/css" href="touchscreen.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)

_X_SEGMENTS = 8
_Y_SEGMENTS = 8


class TouchEvent(object):
  """The class to store touchscreen touch event."""

  def __init__(self):
    self.x = None
    self.y = None
    self.sync = None
    self.leave = None

  def Clear(self):
    self.x = self.y = self.sync = self.leave = None


class TouchscreenTest(unittest.TestCase):
  """Tests the function of touchscreen.

  The test detects that finger has left on every sector of touchscreen.

  Properties:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.x_max: max grid value of horizontal movement.
    self.y_max: max grid valud of vertical movement.
    self.touchscreen_device_name: This can be probed from evdev.
    self.touch_event: the detected touch event. The event will be drew
        and reset if there are a sync event AND a leave event.
    self.checked: user has already pressed spacebar to check touchscreen.
  """
  ARGS = [
      Arg('touchscreen_event_id', int, 'Touchscreen input event id.',
          default=None, optional=True),
      Arg('timeout_secs', (int, type(None)),
          'Timeout for the test, None for no timeout.', default=20)
  ]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendHTML(_HTML_TOUCHSCREEN)
    self.ui.CallJSFunction('setupTouchscreenTest', _ID_CONTAINER, _X_SEGMENTS,
                           _Y_SEGMENTS)

    # Initialize properties
    self.x_max = None
    self.y_max = None
    self.touchscreen_device_name = None
    self.touch_event = TouchEvent()
    self.checked = False
    self.dispatcher = None

    if self.args.touchscreen_event_id is None:
      touchscreen_devices = evdev_utils.GetTouchscreenDevices()
      assert len(touchscreen_devices) == 1, (
          'Multiple touchscreen devices detected')
      self.touchscreen_device = touchscreen_devices[0]
    else:
      self.touchscreen_device = evdev.InputDevice(
          '/dev/input/event%d' % self.args.touchscreen_event_id)

    if self.args.timeout_secs is not None:
      logging.info('start countdown timer daemon thread')
      countdown_timer.StartCountdownTimer(
          self.args.timeout_secs,
          lambda: self.ui.CallJSFunction('failTest'),
          self.ui,
          ['touchscreen-countdown-timer',
           'touchscreen-full-screen-countdown-timer'])

  def tearDown(self):
    """Restores the touchscreen."""
    if self.dispatcher is not None:
      self.dispatcher.close()
    self.touchscreen_device.ungrab()

  def GetSpec(self):
    """Gets device name, x_max and y_max from evdev."""
    self.touchscreen_device_name = self.touchscreen_device.name
    ev_abs_dict = dict(
        self.touchscreen_device.capabilities()[evdev.ecodes.EV_ABS])
    self.x_max = ev_abs_dict[evdev.ecodes.ABS_MT_POSITION_X].max
    self.y_max = ev_abs_dict[evdev.ecodes.ABS_MT_POSITION_Y].max
    logging.info('get device %s spec , x_max = %d, y_max = %d',
                 self.touchscreen_device_name, self.x_max, self.y_max)

  def ProcessTouchEvent(self, event):
    """Processes touch events.

    Processes event, update touch_event and draws it upon receving sync event or
    leave event.

    Args:
      event: the event to process.
    """
    if event.code == evdev.ecodes.ABS_MT_POSITION_X:
      self.touch_event.x = event.value
    elif event.code == evdev.ecodes.ABS_MT_POSITION_Y:
      self.touch_event.y = event.value
    elif event.code == evdev.ecodes.ABS_MT_TRACKING_ID:
      if event.value > 0:
        self.touch_event.leave = False
      elif event.value == -1:
        self.touch_event.leave = True
    elif event.code == evdev.ecodes.SYN_REPORT:
      self.touch_event.sync = True
    elif event.code == evdev.ecodes.ABS_MT_SLOT:
      self.ui.CallJSFunction('twoFingersException')

    if self.touch_event.sync or self.touch_event.leave:
      self.DrawTouchEvent()
      self.touch_event.Clear()

  def DrawTouchEvent(self):
    """Marks a scroll sector as tested or a move sector as tested."""
    if self.touch_event.x and self.touch_event.y:
      x_ratio = float(self.touch_event.x) / float(self.x_max + 1)
      y_ratio = float(self.touch_event.y) / float(self.y_max + 1)
      self.MarkSectorTested(x_ratio, y_ratio)

  def MarkSectorTested(self, x_ratio, y_ratio):
    """Marks a sector as tested.

    Gets the segment from x_ratio and y_ratio then calls Javascript to
    mark the sector as tested.
    """
    x_segment = int(x_ratio * _X_SEGMENTS)
    y_segment = int(y_ratio * _Y_SEGMENTS)
    logging.info('mark x-%d y-%d sector tested', x_segment, y_segment)
    self.ui.CallJSFunction('markSectorTested', x_segment, y_segment)

  def OnSpacePressed(self):
    """Calls JS function to switch display on/off.

    Delay touchscreen_device.grab() to here so we can use touchscreen to click
    the space button to start the test.
    """
    self.ui.CallJSFunction('switchDisplayOnOff')

    if not self.checked:
      self.checked = True
      self.GetSpec()
      self.touchscreen_device.grab()
      logging.info('start monitor daemon thread')
      self.dispatcher = evdev_utils.InputDeviceDispatcher(
          self.touchscreen_device, self.ProcessTouchEvent)
      self.dispatcher.StartDaemon()

  def OnFailPressed(self):
    """Fails the test."""
    self.ui.CallJSFunction('failTest')

  def runTest(self):
    self.ui.BindKey(test_ui.SPACE_KEY, lambda _: self.OnSpacePressed())
    self.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnFailPressed())
    self.ui.Run()
