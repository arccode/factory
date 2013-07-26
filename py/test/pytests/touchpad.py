# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to test the functionality of touchpad.

dargs:
  touchpad_event_id: Touchpad input event id. (default: None)
  timeout_secs: Timeout for the test. (default: 30 seconds)
"""

import evdev
import logging
import re
import subprocess
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
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

#Event: time 1352876895.258289, type 3 (EV_ABS), code 47 (ABS_MT_SLOT), value 0
_RE_EVTEST_SCROLL_MOVE_EVENT = re.compile(
    _RE_ABS + r'\(ABS_MT_SLOT\), value (.*?)$')

#Event: time 1352876919.881157, type 1 (EV_KEY), code 333
# (BTN_TOOL_DOUBLETAP), value 0
_RE_EVTEST_DOUBLE_TAP_EVENT = re.compile(
    _RE_KEY + r'\(BTN_TOOL_DOUBLETAP\), value (.*?)$')

#Event: time 1352876943.148015, type 1 (EV_KEY), code 272 (BTN_LEFT), value 0
_RE_EVTEST_BTN_LEFT_EVENT = re.compile(
    _RE_KEY + r'\(BTN_LEFT\), value (.*?)$')

#Event: time 1352876943.148015, type 1 (EV_KEY), code 273 (BTN_RIGHT), value 0
_RE_EVTEST_BTN_RIGHT_EVENT = re.compile(
    _RE_KEY + r'\(BTN_RIGHT\), value (.*?)$')

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

#Supported events:
#  Event type 0 (EV_SYN)
#  Event type 1 (EV_KEY)
#    Event code 272 (BTN_LEFT)
#    Event code 273 (BTN_RIGHT)
_RE_EVTEST_BTN_RIGHT = re.compile(
    r'\(BTN_RIGHT\)$', flags=re.MULTILINE)

_ID_CONTAINER = 'touchpad-test-container'
_ID_COUNTDOWN_TIMER = 'touchpad-test-timer'

# The layout contains one div for touchpad touch and scroll,
# one table for left/right click, and one div for countdown timer.
_HTML_TOUCHPAD = '''
<div id="%s" style="position: relative; width: 100%%; height: 60%%;"></div>
<table style="width: 100%%; height: 30%%;">
  <tbody>
    <tr>
      <td style="width: 65%%;">
        <table id="quadrant_table" style="width: 100%%;">
          <tbody>
            <tr>
              <td>
                <div id="quadrant2" class="touchpad-test-sector-untested" align="center">
                  Click Left-Top Corner
                  <div id="quadrant2_count" align="center">0/3</div>
                </div>
              </td>
              <td>
                <div id="quadrant1" class="touchpad-test-sector-untested" align="center">
                  Click Right-Top Corner
                  <div id="quadrant1_count" align="center">0/3</div>
                </div>
              </td>
            </tr>
            <tr>
              <td>
                <div id="quadrant3" class="touchpad-test-sector-untested" align="center">
                  Click Left-Bottom Corner
                  <div id="quadrant3_count" align="center">0/3</div>
                </div>
              </td>
              <td>
                <div id="quadrant4" class="touchpad-test-sector-untested" align="center">
                  Click Right-Bottom Corner
                  <div id="quadrant4_count" align="center">0/3</div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </td>
      <td>
        <table style="width: 100%%;">
          <tbody>
            <tr>
              <td align="right" valign="center">
                <div id="left-circle" class="touchpad-test-circle-untested"></div>
              </td>
              <td align="left" valign="center">
                <div id="left-text-cell"></div>
              </td>
              <td align="right" valign="center">
                <div id="right-circle" class="touchpad-test-circle-untested"></div>
              </td>
              <td align="left" valign="center">
                <div id="right-text-cell"></div>
              </td>
            </tr>
          </tbody>
        </table>
      </td>
    </tr>
  </tbody>
</table>
<div id="%s"></div>
''' % (_ID_CONTAINER, _ID_COUNTDOWN_TIMER)

# The styles for each item on ui.
# For sectors (moving and scrolling event):
#   touchpad-test-sector-untested: sector not touched.
#   touchpad-test-sector-tested: sector touched.
# For circles (click event):
#   touchpad-test-circle-untested: the style to show before click.
#   touchpad-test-circle-down: click down.
#   touchpad-test-circle-tested: release click.
_TOUCHPAD_TEST_DEFAULT_CSS = '''
    #touchpad-test-timer { font-size: 2em; }
    .touchpad-test-sector-untested {
      background-color: gray;
      height: 100%; }
    .touchpad-test-sector-tested {
      background-color: green; height: 100%;
      opacity: 0.5; }
    .touchpad-test-circle-untested {
      border: 3px solid gray;
      border-radius: 50%;
      width: 20px; height: 20px;
      box-sizing: border-box; }
    .touchpad-test-circle-down {
      border: 3px solid yellow;
      border-radius: 50%;
      width: 20px; height: 20px;
      box-sizing: border-box; }
    .touchpad-test-circle-tested {
      border: 3px solid green;
      border-radius: 50%;
      width: 20px; height: 20px;
      box-sizing: border-box; }
'''

class UpDown:
  '''
  The class to represent Up or Down event for KEY input.
  The value is the same as value from evtest KEY event,
  where "0" is up and "1" is down.
  '''
  def __init__(self):
    pass
  Up = "0"
  Down = "1"


class Quadrant:
  '''
  The class is to update quadrant information according to x_ratio and y_ratio
  Quadrant 1 is Right-Top Corner
  Quadrant 2 is Left-Top Corner
  Quadrant 3 is Left-Bottom Corner
  Quadrant 4 is Right-Bottom Corner
  '''
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

class MoveEvent:
  '''The class to store touchpad move event.'''
  def __init__(self):
    self.x = None
    self.y = None
    self.scroll = None
    self.sync = None

  def Clear(self):
    self.x = self.y = self.scroll = self.sync = None


class ClickEvent:
  '''
  The class to store touchpad click event. Double tap event is also stored to
  catch double click event.
  The logic to recognize double click:
    btn_left is down and
  '''
  def __init__(self):
    self.double_tap = None
    self.btn_left = None
    self.btn_right = None

  def ClearBtnLeft(self):
    self.btn_left = None

  def ClearBtnRight(self):
    self.btn_right = None


def GetProp(message, pattern):
  '''
  Gets the property from searching pattern in message.
  Args:
    message: A string to search for pattern.
    pattern: A regular expression object which will capture a value if pattern
             can be found.
  '''
  val = None
  obj = pattern.search(message)
  if obj:
    val = obj.group(1)
  return val

def CheckUpdate(new_value, old_value):
  '''Returns new_value if new_value is not None, return old_value otherwise.'''
  return new_value if new_value else old_value

class TouchpadTest(unittest.TestCase):
  '''
  Tests the function of touchpad. The test checks the following function:
    1. Detect finger on every sector of touchpad.
    2. Two finger scrolling.
    3. Single click.
    4. Either double click or right click.
  Properties:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.x_max: max grid value of horizontal movement.
    self.y_max: max grid valud of vertical movement.
    self.touchpad_device_name: This can be probed from evtest. We need touchpad
        device name to enable/disable it using xinput.
    self.move_event: the detected move event. The event will be drew
        and reset upon sync event.
    self.click_event: the detected click event. The event will be drew for each
        detected btn_left or btn_right up and down. btn_left or btn_right will
        get reset upon drawing. Note that double_tap will not get reset
        upon drawing since we have to keep double_tap value for the case that
        two fingers stay on the touchpad.
    self.touchpad_has_right_btn: for touchpad with right button, we don't want
        to process double click. We will only process right_btn and left_btn.
    self.monitor_process: the evtest process to get touchpad input.
        This should get terminated when test stops.
    self.touchpad_event_path: The path of input device like /dev/input/event1.
    self.quadrant: This represents the current quadrant of mouse.
  '''
  ARGS = [
    Arg('touchpad_event_id', int, 'Touchpad input event id. The test will probe'
        ' for event id if it is not given.', default=None, optional=True),
    Arg('timeout_secs', int, 'Timeout for the test.', default=20),
    Arg('number_to_click', int, 'Target number to click.', default=10),
    Arg('number_to_quadrant', int, 'Target number to click for each quadrant.',
        default=3),
    Arg('x_segments', int, 'Number of X axis segments to test.', default=5),
    Arg('y_segments', int, 'Number of Y axis segments to test.', default=5)
  ]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_TOUCHPAD_TEST_DEFAULT_CSS)
    self.template.SetState(_HTML_TOUCHPAD)
    self.ui.CallJSFunction('setupTouchpadTest', _ID_CONTAINER,
        self.args.x_segments, self.args.y_segments, self.args.number_to_click,
        self.args.number_to_quadrant)

    # Initialize properties
    self.x_max = None
    self.y_max = None
    self.touchpad_device_name = None
    self.move_event = MoveEvent()
    self.click_event = ClickEvent()
    self.touchpad_has_right_btn = False
    self.monitor_process = None
    self.quadrant = Quadrant()
    if self.args.touchpad_event_id is None:
      self.touchpad_event_path = self.ProbeEventSource()
    else:
      self.touchpad_event_path = ('/dev/input/event' +
                                  str(self.args.touchpad_event_id))

    logging.info('start monitor daemon thread')
    StartDaemonThread(target=self.MonitorEvtest)
    logging.info('start countdown timer daemon thread')
    StartCountdownTimer(self.args.timeout_secs,
                        lambda: self.ui.CallJSFunction('failTest'),
                        self.ui,
                        _ID_COUNTDOWN_TIMER)

  def ProbeEventSource(self):
    """Probes for touch event path.

    Touch device has type EV_ABS, and there is a code ABS_MT_POSITION_X in
    the first element of one of its values.
    It also has type EV_KEY, in which there is a code BTN_LEFT in its values.
    """
    for dev in map(evdev.InputDevice, evdev.list_devices()):
      event_type_code = dev.capabilities()
      logging.info('capabilities, %s', event_type_code)
      if not (evdev.ecodes.EV_KEY in event_type_code and
              evdev.ecodes.BTN_LEFT in event_type_code[evdev.ecodes.EV_KEY]):
        continue
      if (evdev.ecodes.EV_ABS in event_type_code):
        codes = [x[0] for x in event_type_code[evdev.ecodes.EV_ABS]]
        if evdev.ecodes.ABS_MT_POSITION_X in codes:
          logging.info('Probed device path: %s; name %s', dev.fn, dev.name)
          return dev.fn

  def tearDown(self):
    '''
    Terminates the running process or we'll have trouble stopping the
    test. Enable the touchpad at X to enable touchpad function in test ui.
    '''
    if self.monitor_process.poll() is None:
      self.monitor_process.terminate()
    self.EnableTouchpadX(True)

  def MonitorEvtest(self):
    '''
    Starts evtest process, gets the spec of touchpad, disables touchpad at X,
    and monitors touchpad events from output of evtest.
    '''
    self.monitor_process = Spawn(['evtest', self.touchpad_event_path],
                                 stdout=subprocess.PIPE)
    self.GetSpec()
    self.EnableTouchpadX(False)
    self.MonitorEvent()

  def GetSpecMessages(self):
    '''
    Gets spec messages from evtest output before testing starts.
    Messages are like:

    Input driver version is 1.0.1
    Input device ID: bus 0x18 vendor 0x0 product 0x0 version 0x0
    Input device name: "TOUCHPAD_NAME"
    Supported events:
    Event type 0 (EV_SYN)
    Event type 1 (EV_KEY)
      Event code 272 (BTN_LEFT)
      Event code 273 (BTN_RIGHT)
      Event code 325 (BTN_TOOL_FINGER)
      Event code 328 (?)
      Event code 330 (BTN_TOUCH)
      Event code 333 (BTN_TOOL_DOUBLETAP)
      Event code 334 (BTN_TOOL_TRIPLETAP)
      Event code 335 (BTN_TOOL_QUADTAP)
    Event type 3 (EV_ABS)
        ...
        ...
      Event code 53 (ABS_MT_POSITION_X)
      Value      0
      Min        0
      Max     2040
      Resolution      20
    Event code 54 (ABS_MT_POSITION_Y)
      Value      0
      Min        0
      Max     1360
      Resolution      20
        ...
        ...
    Testing ... (interrupt to exit)
    '''
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
    '''Gets device name , btn_right, x_max and y_max from evtest output'''
    spec_messages = self.GetSpecMessages()
    logging.info('parsing spec message...\n %s', spec_messages)
    self.x_max = GetProp(spec_messages, _RE_EVTEST_X_MAX)
    self.y_max = GetProp(spec_messages, _RE_EVTEST_Y_MAX)
    self.touchpad_device_name = GetProp(spec_messages, _RE_EVTEST_NAME)
    if _RE_EVTEST_BTN_RIGHT.search(spec_messages):
      self.touchpad_has_right_btn = True

    logging.info('get device %s spec right_btn = %s, x_max = %s, y_max = %s',
                 self.touchpad_device_name, self.touchpad_has_right_btn,
                 self.x_max, self.y_max)

  def EnableTouchpadX(self, enable):
    '''Enables/Disables touchpad at the X server.'''
    Spawn(['xinput', 'set-prop', self.touchpad_device_name,
           'Device Enabled', '1' if enable else '0'], check_call=True)

  def MonitorEvent(self):
    '''Gets event message from evtest and process it'''
    while True:
      event_message = self.monitor_process.stdout.readline()
      self.ProcessMoveEvent(event_message)
      self.ProcessClickEvent(event_message)

  def ProcessLeftAndRightClickEvent(self):
    '''Draws left click event or right click event.'''
    self.DrawLeftClick(self.click_event.btn_left)
    self.click_event.ClearBtnLeft()
    self.DrawRightClick(self.click_event.btn_right)
    self.click_event.ClearBtnRight()

  def ProcessSingleAndDoubleClickEvent(self):
    '''Draws single click event or double click event.'''
    if self.click_event.double_tap == UpDown.Down:
      self.DrawDoubleClick(self.click_event.btn_left)
      self.click_event.ClearBtnLeft()
    else:
      self.DrawSingleClick(self.click_event.btn_left)
      self.click_event.ClearBtnLeft()

  def ProcessClickEvent(self, event_message):
    '''
    Parses event_message, updates click_event and draws it.
    Args:
      event_message: one line of event message from evtest.
    '''
    self.ParseMessageAndUpdateClickEvent(event_message)
    if self.touchpad_has_right_btn:
      self.ProcessLeftAndRightClickEvent()
    else:
      self.ProcessSingleAndDoubleClickEvent()

  def ParseMessageAndUpdateClickEvent(self, event_message):
    '''
    Parses event_message and updates click_event.
    Args:
      event_message: one line of event message from evtest.
    '''
    self.click_event.double_tap = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_DOUBLE_TAP_EVENT),
        self.click_event.double_tap)
    self.click_event.btn_left = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_BTN_LEFT_EVENT),
        self.click_event.btn_left)
    self.click_event.btn_right = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_BTN_RIGHT_EVENT),
        self.click_event.btn_right)

  def ProcessMoveEvent(self, event_message):
    '''
    Parses event_message, update move_event and draws it upon receving
    sync event.
    Args:
      event_message: one line of event message from evtest.
    '''
    self.ParseMessageAndUpdateMoveEvent(event_message)
    if self.move_event.sync:
      self.DrawMoveEvent()
      self.move_event.Clear()

  def DrawMoveEvent(self):
    '''
    Marks a scroll sector as tested or a move sector as tested.
    '''
    if self.move_event.x:
      x_ratio = float(self.move_event.x) / float(self.x_max)
    if self.move_event.y:
      y_ratio = float(self.move_event.y) / float(self.y_max)

    if self.move_event.x and self.move_event.y:
      self.quadrant.UpdateQuadrant(x_ratio, y_ratio)

    if self.move_event.scroll and self.move_event.y:
      self.MarkScrollSectorTested(y_ratio)
    elif self.move_event.x and self.move_event.y:
      self.MarkSectorTested(x_ratio, y_ratio)

  def ParseMessageAndUpdateMoveEvent(self, event_message):
    '''
    Parses event_message and updates move_event.
    Args:
      event_message: one line of event message from evtest.
    '''
    self.move_event.x = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_X_MOVE_EVENT), self.move_event.x)
    self.move_event.y = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_Y_MOVE_EVENT), self.move_event.y)
    self.move_event.scroll = CheckUpdate(
        GetProp(event_message, _RE_EVTEST_SCROLL_MOVE_EVENT),
        self.move_event.scroll)
    if _RE_EVTEST_SYNREPORT.search(event_message):
      self.move_event.sync = True

  def DrawSingleClick(self, up_down):
    '''
    Draws single click event by calling javascript function.
    Args:
      up_down: UpDown.Up or Updown.Down or None.
    '''
    if up_down == UpDown.Up:
      logging.info('mark single click up')
      self.ui.CallJSFunction('markSingleClickUp', self.quadrant.quadrant)
    elif up_down == UpDown.Down:
      logging.info('mark single click down')
      self.ui.CallJSFunction('markSingleClickDown', self.quadrant.quadrant)

  def DrawDoubleClick(self, up_down):
    '''
    Draws double click event by calling javascript function.
    Args:
      up_down: UpDown.Up or Updown.Down or None.
    '''
    if up_down == UpDown.Up:
      logging.info('mark double click up')
      self.ui.CallJSFunction('markDoubleClickUp')
    elif up_down == UpDown.Down:
      logging.info('mark double click down')
      self.ui.CallJSFunction('markDoubleClickDown')

  def DrawLeftClick(self, up_down):
    '''
    Draw left click event. For now we reuse DrawSingleClick.
    Args:
      up_down: UpDown.Up or Updown.Down or None.
    '''
    self.DrawSingleClick(up_down)

  def DrawRightClick(self, up_down):
    '''
    Draw right click event. For now we reuse DrawDoubleClick.
    Args:
      up_down: UpDown.Up or Updown.Down or None.
    '''
    self.DrawDoubleClick(up_down)

  def MarkScrollSectorTested(self, y_ratio):
    '''
    Gets the scroll sector from y_ratio then calls Javascript to mark the sector
    as tested.
    '''
    y_segment = int(y_ratio * self.args.y_segments)
    logging.info('mark %d scroll segment tested', y_segment)
    self.ui.CallJSFunction('markScrollSectorTested', y_segment)


  def MarkSectorTested(self, x_ratio, y_ratio):
    '''
    Gets the segment from x_ratio and y_ratio then calls Javascript to
    mark the sector as tested.
    '''
    x_segment = int(x_ratio * self.args.x_segments)
    y_segment = int(y_ratio * self.args.y_segments)
    logging.info('mark x-%d y-%d sector tested', x_segment, y_segment)
    self.ui.CallJSFunction('markSectorTested', x_segment, y_segment)

  def runTest(self):
    self.ui.Run()
