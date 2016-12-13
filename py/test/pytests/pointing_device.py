# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test generic pointing device.

The built-in touchpad is disabled during the test for verifying other
pointing device's functionality.
"""

import string
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


_MSG_TEST_TITLE = test_ui.MakeLabel('Non-touchpad Pointing Device Test',
                                    u'非触控板之指向装置测试')
_MSG_INSTRUCTION = test_ui.MakeLabel(
    'Please move the pointer over four quarters.', u'请移動鼠標至此文字四周')
_MSG_MOVE_HERE = test_ui.MakeLabel('Move Here!', u'移動鼠標至此')
_MSG_INSTRUCTION_CLICK = test_ui.MakeLabel(
    'Please click the pointing device.',
    u'请按下指向装置左键')
_MSG_INSTRUCTION_RIGHT_CLICK = test_ui.MakeLabel(
    'Please right-click the pointing device.',
    u'请按下指向装置右键')
_MSG_INSTRUCTION_SCROLL_UP = test_ui.MakeLabel(
    'Please scroll up with the pointing device.',
    u'请用指向装置向上卷动')
_MSG_INSTRUCTION_SCROLL_DOWN = test_ui.MakeLabel(
    'Please scroll down with the pointing device.',
    u'请用指向装置向下卷动')

_CSS = """
.pd-quarter { height: 50%; width: 50%; position: absolute; display: table;}
#pd-quarter-1 { top: 0; right: 0; }
#pd-quarter-2 { top: 0; left: 0; }
#pd-quarter-3 { bottom: 0; left: 0; }
#pd-quarter-4 { bottom: 0; right: 0; }
#pd-instruction { font-size: 24px; padding-bottom: 12px;}
"""

_INSTRUCTION_HTML = (
    '<div id="pd-instruction">%s</div>') % _MSG_INSTRUCTION


def _QuarterHTML(nth_quarter):
  """Generates a div of a quarter area.

  Args:
    nth_quarter: quarter of [1, 4].
  """
  return string.Template(
      "<div id='$quarter_id' class='pd-quarter'\n"
      "     onmouseover='pd.quarterMouseOver(\"$quarter_id\");'>\n"
      "  <div class='test-vcenter-inner'>$caption</div>\n"
      "</div>").substitute(quarter_id='pd-quarter-%d' % nth_quarter,
                           caption=_MSG_MOVE_HERE)


def _GenerateJS(scroll, scroll_threshold):
  """Generates a JS code for the test.

  Args:
    scroll: True to append scroll test after right-click test.
    scroll_threshold: threshold for recognizing scroll event.

  Returns:
    JS code.
  """
  setup = (
      "var pd = {};\n"
      "pd.setInstruction = function(instruction) {\n"
      "  document.getElementById('pd-instruction').innerHTML = instruction;\n"
      "};\n"
      "// Prevent right click from popping up menu.\n"
      "document.oncontextmenu = function() { return false; }")
  mouseover_test = (
      "pd.quarterTouched = {};\n"
      "pd.remainingQuarters = 4;\n"
      "pd.quarterMouseOver = function(id) {\n"
      "  if (id in pd.quarterTouched) {\n"
      "    return;\n"
      "  }\n"
      "  document.getElementById(id).onmouseover = '';\n"
      "  document.getElementById(id).style.display = 'none';\n"
      "  pd.quarterTouched[id] = true;\n"
      "  pd.remainingQuarters -= 1;\n"
      "  if (pd.remainingQuarters == 0) {\n"
      "    pd.startClickTest();\n"
      "  }\n"
      "};")
  click_test = (
      "pd.startClickTest = function() {\n"
      "  pd.setInstruction('%s');\n"
      "  document.getElementById('state').onclick = function(event) {\n"
      "    event.target.onclick = '';\n"
      "    pd.startRightClickTest();\n"
      "  };\n"
      "};") % _MSG_INSTRUCTION_CLICK
  right_click_test = (
      "pd.startRightClickTest = function() {\n"
      "  pd.setInstruction('%s');\n"
      "  document.getElementById('state').oncontextmenu = function(event) {\n"
      "    if (event.which == 3) {\n"
      "      event.target.oncontextmenu = '';\n"
      "      %s\n"
      "    }\n"
      "    return false;\n"
      "  };\n"
      "};") % (_MSG_INSTRUCTION_RIGHT_CLICK,
               'pd.startUpScrollTest();' if scroll else 'window.test.pass();')

  js = [setup, mouseover_test, click_test, right_click_test]
  if scroll:
    js.append(string.Template(
        "pd.startUpScrollTest = function() {\n"
        "  pd.setInstruction('$up_inst');\n"
        "  document.addEventListener('mousewheel', function(e) {\n"
        "    if (e.wheelDelta >= $delta) {\n"
        "      pd.startDownScrollTest();\n"
        "    }});\n"
        "};\n"
        "pd.startDownScrollTest = function() {\n"
        "  pd.setInstruction('$down_inst');\n"
        "  document.addEventListener('mousewheel', function(e) {\n"
        "    if (e.wheelDelta <= -$delta) {\n"
        "      window.test.pass();\n"
        "    }});\n"
        "};").substitute(up_inst=_MSG_INSTRUCTION_SCROLL_UP,
                         down_inst=_MSG_INSTRUCTION_SCROLL_DOWN,
                         delta=scroll_threshold))
  return '\n'.join(js)


class PointingDeviceUI(ui_templates.OneSection):
  """Composes an UI for pointing device test.

  Args:
    ui: UI object.
    scroll: True to add scroll test.
    scroll_thresold: Threshold for recognizing scroll event.
  """

  def __init__(self, ui, scroll, scroll_threshold):
    super(PointingDeviceUI, self).__init__(ui)
    ui.AppendCSS(_CSS)
    ui.RunJS(_GenerateJS(scroll, scroll_threshold))

  def AppendHTML(self, html):
    self.SetState(html, append=True)

  def AddQuarters(self):
    """Adds four quarter area div for pointing device movement test.
    """
    for quarter in xrange(1, 5):
      self.AppendHTML(_QuarterHTML(quarter))

  def Run(self):
    self._ui.Run()

  def Fail(self, reason):
    self._ui.Fail(reason)


class PointingDeviceTest(unittest.TestCase):
  """Generic pointing device test.

  It draws four buttons and the test will pass after four buttons are
  clicked and a right-click is triggered.
  """
  ARGS = [
      Arg('touchpad', str, 'TouchPad device name in xinput.', optional=False),
      Arg('test_scroll', bool, "Test device's scroll feature.", default=False),
      Arg('scroll_threshold', int, 'Threshold for recognizing scroll event.',
          default=50)
  ]

  def setUp(self):
    self._ui = PointingDeviceUI(test_ui.UI(), self.args.test_scroll,
                                self.args.scroll_threshold)
    if not self.SetXinputDeviceEnabled(self.args.touchpad, False):
      self._ui.Fail('Failed to disable touchpad.')

  def tearDown(self):
    if not self.SetXinputDeviceEnabled(self.args.touchpad, True):
      self._ui.Fail('Failed to enable touchpad.')

  def runTest(self):
    ui = self._ui
    ui.SetTitle(_MSG_TEST_TITLE)
    ui.AddQuarters()
    ui.AppendHTML(_INSTRUCTION_HTML)
    ui.BindStandardKeys(bind_pass_key=False, bind_fail_key=True)
    ui.Run()

  def SetXinputDeviceEnabled(self, device, enabled):
    """Sets 'Device Enabled' props for xinput device.

    Args:
      device: xinput device name.
      enabled: True to enable the device; otherwise, disable.

    Returns:
      False if failed.
    """
    if 'Device Enabled' not in process_utils.SpawnOutput(
        ['xinput', 'list-props', device], log_stderr_on_error=True):
      return False

    return process_utils.Spawn(
        ['xinput', 'set-prop', device, 'Device Enabled', str(int(enabled))],
        log_stderr_on_error=True).returncode == 0
