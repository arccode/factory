# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the functionality of touchscreen.

dargs:
  touchscreen_event_id: Touchscreen input event id. (default: 7)
"""

import logging
import re
import subprocess
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils.process_utils import Spawn


#Event: time 1352876832.935291, type 3 (EV_ABS), code 53
_RE_ABS = r'^Event: time .*?, type .*? \(EV_ABS\), code .*? '

#Event: time 1352876919.881157, type 1 (EV_KEY), code 333
_RE_KEY = r'^Event: time .*?, type .*? \(EV_KEY\), code .*? '

#Event: time 1352876832.935301, -------------- SYN_REPORT ------------
_RE_EVTEST_SYNREPORT = re.compile(
    r'^Event: time .*?, -* SYN_REPORT -*$')

#Event: time 1352876832.935291, type 3 (EV_ABS), code 53
# (ABS_MT_POSITION_X), value 436
_RE_EVTEST_X_MOVE_EVENT = re.compile(
    _RE_ABS + r'\(ABS_MT_POSITION_X\), value (.*?)$')

#Event: time 1352876832.935292, type 3 (EV_ABS), code 54
# (ABS_MT_POSITION_Y), value 764
_RE_EVTEST_Y_MOVE_EVENT = re.compile(
    _RE_ABS + r'\(ABS_MT_POSITION_Y\), value (.*?)$')

#Event: time 1356667900.951634, type 3 (EV_ABS), code 47
# (ABS_MT_SLOT), value 0
# This event means there are multiple fingers.
_RE_EVTEST_SLOT_EVENT = re.compile(
    _RE_ABS + r'\(ABS_MT_SLOT\), value (.*?)$')

#Event: time 1356670305.408711, type 3 (EV_ABS), code 57
# (ABS_MT_TRACKING_ID), value -1
# Value > 0 in this event means new finger start touching.
# Value -1 in this event means finger left touchscreen.
_RE_EVTEST_TRACKING_ID_EVENT = re.compile(
    _RE_ABS + r'\(ABS_MT_TRACKING_ID\), value (.*?)$')

#    Event code 53 (ABS_MT_POSITION_X)
#      Value      0
#      Min        0
#      Max     2040
#      Resolution      20
_RE_EVTEST_X_MAX = re.compile(
    r'\(ABS_MT_POSITION_X\).*?Max[\s]*([\d]*)', flags=re.DOTALL)

#    Event code 54 (ABS_MT_POSITION_Y)
#      Value      0
#      Min        0
#      Max     1360
#      Resolution      20
_RE_EVTEST_Y_MAX = re.compile(
    r'\(ABS_MT_POSITION_Y\).*?Max[\s]*([\d]*)', flags=re.DOTALL)

#Testing ... (interrupt to exit)
_RE_EVTEST_START_TESTING = re.compile(
    r'Testing ...')

#Input device name: "XXXXXX"
_RE_EVTEST_NAME = re.compile(
    r'Input device name: "(.*?)"$', flags=re.MULTILINE)

_ID_CONTAINER = 'touchscreen-test-container'

# The style is in touchscreen.css
# The layout contains one div for touchscreen.
_HTML_TOUCHSCREEN = (
    '<link rel="stylesheet" type="text/css" href="touchscreen.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)

_X_SEGMENTS = 8
_Y_SEGMENTS = 8


class TouchEvent:
  """The class to store touchscreen touch event."""
  def __init__(self):
    self.x = None
    self.y = None
    self.sync = None
    self.leave = None

  def Clear(self):
    self.x = self.y = self.sync = self.leave = None


def GetProp(message, pattern):
  """Gets the property from searching pattern in message.

  Args:
    message: A string to search for pattern.
    pattern: A regular expression object which will capture a value if pattern
             can be found.
  """
  val = None
  obj = pattern.search(message)
  if obj:
    val = obj.group(1)
  return val


def CheckUpdate(new_value, old_value):
  """Returns new_value if new_value is not None, return old_value otherwise."""
  return new_value if new_value else old_value


class TouchscreenTest(unittest.TestCase):
  """Tests the function of touchscreen.

  The test detects that finger has left on every sector of touchscreen.

  Properties:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.x_max: max grid value of horizontal movement.
    self.y_max: max grid valud of vertical movement.
    self.touchscreen_device_name: This can be probed from evtest.
        We need touchscreen device name to enable/disable it using xinput.
    self.touch_event: the detected touch event. The event will be drew
        and reset if there are a sync event AND a leave event.
    self.monitor_process: the evtest process to get touchscreen input.
        This should get terminated when test stops.
    self.checked: user has already pressed spacebar to check touchscreen.
  """
  ARGS = [
    Arg('touchscreen_event_id', int, 'Touchscreen input event id.',
        default=7)
  ]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendHTML(_HTML_TOUCHSCREEN)
    self.ui.CallJSFunction('setupTouchscreenTest', _ID_CONTAINER,
        _X_SEGMENTS, _Y_SEGMENTS)

    # Initialize properties
    self.x_max = None
    self.y_max = None
    self.touchscreen_device_name = None
    self.touch_event = TouchEvent()
    self.monitor_process = None
    self.checked = False
    # Record the state of touchscreen before test starts so we can restore it
    # after the test.
    self.touchscreen_device_id = utils.GetTouchscreenDeviceIds()[0]
    self.touchscreen_enabled = utils.IsXinputDeviceEnabled(
        self.touchscreen_device_id)

    logging.info('start monitor daemon thread')
    StartDaemonThread(target=self.MonitorEvtest)

  def tearDown(self):
    """Terminates the running process or we'll have trouble stopping the test.

    Also restores the touchscreen at X.
    """
    self.TerminateProcess()
    self.EnableTouchscreenX(self.touchscreen_enabled)

  def MonitorEvtest(self):
    """Monitors evtest events.

    Starts evtest process, gets the spec of touchscreen, disables touchscreen
    at X, and monitors touchscreen events from output of evtest.
    """
    self.monitor_process = Spawn(['evtest', '/dev/input/event%d' % (
                                  self.args.touchscreen_event_id)],
                                  stdout=subprocess.PIPE)
    self.GetSpec()
    self.EnableTouchscreenX(False)
    self.MonitorEvent()

  def GetSpecMessages(self):
    """Gets spec messages from evtest output before testing starts.

    Messages are like:

      Input driver version is 1.0.1
      Input device ID: bus 0x18 vendor 0x0 product 0x0 version 0x0
      Input device name: "<TOUCHSCREEN_NAME>"
      Supported events:
        Event type 0 (EV_SYN)
        Event type 1 (EV_KEY)
          Event code 330 (BTN_TOUCH)
        Event type 3 (EV_ABS)
          Event code 0 (ABS_X)
            ...
          Event code 1 (ABS_Y)
            ...
          Event code 24 (ABS_PRESSURE)
            ...
          Event code 47 (ABS_MT_SLOT)
            ...
          Event code 48 (ABS_MT_TOUCH_MAJOR)
            ...
          Event code 53 (ABS_MT_POSITION_X)
            Value      0
            Min        0
            Max     <X_RANGE>
            Resolution     <X_RESOLUTION>
          Event code 54 (ABS_MT_POSITION_Y)
            Value      0
            Min        0
            Max     <Y_RANGE>
            Resolution     <Y_RESOLUTION>
          Event code 57 (ABS_MT_TRACKING_ID)
            ...
          Event code 58 (ABS_MT_PRESSURE)
            ...
      Testing ... (interrupt to exit)
    """
    logging.info('getting spec message..')
    spec_message_lines = []
    spec_messages = None
    while True:
      spec_message_line = self.monitor_process.stdout.readline()
      if _RE_EVTEST_START_TESTING.search(spec_message_line):
        spec_messages = ''.join(spec_message_lines)
        break
      else:
        spec_message_lines.append(spec_message_line)
    return spec_messages

  def GetSpec(self):
    """Gets device name, x_max and y_max from evtest output"""
    spec_messages = self.GetSpecMessages()
    logging.info('parsing spec message...\n %s', spec_messages)
    self.x_max = int(GetProp(spec_messages, _RE_EVTEST_X_MAX))
    self.y_max = int(GetProp(spec_messages, _RE_EVTEST_Y_MAX))
    self.touchscreen_device_name = GetProp(spec_messages, _RE_EVTEST_NAME)

    logging.info('get device %s spec , x_max = %d, y_max = %d',
                 self.touchscreen_device_name, self.x_max, self.y_max)

  def EnableTouchscreenX(self, enable):
    """Enables/Disables touchscreen at the X server."""
    utils.SetXinputDeviceEnabled(self.touchscreen_device_id, enable)

  def MonitorEvent(self):
    """Gets event message from evtest and process it"""
    while True:
      event_message = self.monitor_process.stdout.readline()
      self.ProcessTouchEvent(event_message)

  def ProcessTouchEvent(self, event_message):
    """Processes touch events.

    Parses event_message, update touch_event and draws it upon receving
    sync event or leave event.

    Args:
      event_message: one line of event message from evtest.
    """
    self.ParseMessageAndUpdateTouchEvent(event_message)
    if self.touch_event.sync or self.touch_event.leave:
      self.DrawTouchEvent()
      self.touch_event.Clear()

  def DrawTouchEvent(self):
    """Marks a scroll sector as tested or a move sector as tested."""
    if self.touch_event.x and self.touch_event.y:
      x_ratio = float(self.touch_event.x) / float(self.x_max + 1)
      y_ratio = float(self.touch_event.y) / float(self.y_max + 1)
      self.MarkSectorTested(x_ratio, y_ratio)

  def ParseMessageAndUpdateTouchEvent(self, event_message):
    """Parses event_message and updates touch_event.

    Args:
      event_message: one line of event message from evtest.
    """
    self.touch_event.x = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_X_MOVE_EVENT), self.touch_event.x)
    self.touch_event.y = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_Y_MOVE_EVENT), self.touch_event.y)
    tracking_id_str = GetProp(event_message, _RE_EVTEST_TRACKING_ID_EVENT)
    tracking_id = int(tracking_id_str) if tracking_id_str else None
    if tracking_id > 0:
      self.touch_event.leave = False
    elif tracking_id == -1:
      self.touch_event.leave = True
    if _RE_EVTEST_SYNREPORT.search(event_message):
      self.touch_event.sync = True
    if _RE_EVTEST_SLOT_EVENT.search(event_message):
      self.ui.CallJSFunction('twoFingersException')

  def TerminateProcess(self):
    """Terminates the process if it is running."""
    if self.monitor_process.poll() is None:
      self.monitor_process.terminate()

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
    """Calls JS function to switch display on/off."""
    self.checked = True
    self.ui.CallJSFunction('switchDisplayOnOff')

  def OnFailPressed(self):
    """Fails the test only if self.checked is True."""
    if self.checked:
      self.ui.CallJSFunction('failTest')
      self.checked = False

  def runTest(self):
    self.ui.BindKey(' ', lambda _: self.OnSpacePressed())
    self.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnFailPressed())
    self.ui.Run()
