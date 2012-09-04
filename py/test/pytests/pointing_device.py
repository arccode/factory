# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test generic pointing device.

The built-in touchpad is disabled during the test for verifying other
pointing device's functionality.
"""

from string import Template  # pylint: disable=W0402
import unittest

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import Spawn


_MSG_TEST_TITLE = test_ui.MakeLabel('Non-touchpad Pointing Device Test',
                                    u'非触控板之指向装置测试')
_MSG_INSTRUCTION = test_ui.MakeLabel(
  ('Please use a pointing device other than touchpad to click the four '
   'corner buttons.'),
  u'请使用非触控板之指向装置点击角落的四个按钮')
_MSG_BUTTON_CAPTION = test_ui.MakeLabel('Click me', u'点击')
_MSG_INSTRUCTION_RIGHT_CLICK = test_ui.MakeLabel(
  'Please right-click the pointing device.',
  u'请按下指向装置右键')

_CSS = """
.pd-button-div { font-size: 24px; position: absolute; text-align: center; }
.pd-button { height: 40px; width: 150px; }
#pd-button-tl { top: 30px; left: 30px; }
#pd-button-tr { top: 30px; right: 30px; }
#pd-button-bl { bottom: 30px; left: 30px; }
#pd-button-br { bottom: 30px; right: 30px; }
.instruction { font-size: 24px; padding-bottom: 12px; }
#pd-instruction { font-size: 24px; padding-bottom: 12px; }
"""

_BUTTON_ID = lambda pos: 'pd-button-' + pos

def _ButtonHTML(button_id, caption):
  """Generates a test button."""
  return Template("""
<div id='$button_id' class='pd-button-div'>
  <button class='pd-button' type='button'
          onclick="pd.clickButton('$button_id');">
    <span id='$button_id-caption'>$caption</span>
  </button>
</div>
""").substitute(button_id=button_id, caption=caption)

_INSTRUCTION_HTML = (
  '<div id="pd-instruction">%s</div>') % _MSG_INSTRUCTION

_JS = """
var pd = {};
pd.buttonClicked = {};
pd.remainingButtons = 4;
pd.clickButton = function(id) {
  if (id in pd.buttonClicked) {
    return;
  }
  pd.buttonClicked[id] = true;
  document.getElementById(id).style.display = 'none';
  pd.remainingButtons -= 1;
  if (pd.remainingButtons == 0) {
    pd.startRightClickTest();
  }
};
pd.startRightClickTest = function() {
  document.getElementById('pd-instruction').innerHTML = '%s';
  document.getElementById('state').oncontextmenu = function(event) {
    if (event.which == 3) {
      window.test.pass();
    }};
};
""" % _MSG_INSTRUCTION_RIGHT_CLICK

class PointingDeviceUI(ui_templates.OneSection):
  """Composes an UI for pointing device test.
  """

  def __init__(self, ui):
    super(PointingDeviceUI, self).__init__(ui)
    ui.AppendCSS(_CSS)
    ui.RunJS(_JS)

  def AppendHTML(self, html):
    self.SetState(html, append=True)

  def AddButton(self, caption, position):
    """Adds a button.

    Args:
      caption: Caption of a button.
      position: Position of a button. One of ['tr', 'tl', 'br', 'bl'].
    """
    self.AppendHTML(_ButtonHTML(_BUTTON_ID(position), caption))

  def AddButtons(self, caption):
    """Adds four buttons at corners of the test area.
    """
    for pos in ['tr', 'tl', 'br', 'bl']:
      self.AddButton(caption, pos)

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
    Arg('touchpad', str, 'TouchPad device name in xinput.', optional=False)
  ]

  def __init__(self, *args, **kwargs):
    super(PointingDeviceTest, self).__init__(*args, **kwargs)
    self._ui = PointingDeviceUI(test_ui.UI())

  def setUp(self):
    if not self.SetXinputDeviceEnabled(self.args.touchpad, False):
      self._ui.Fail('Failed to disable touchpad.')

  def tearDown(self):
    if not self.SetXinputDeviceEnabled(self.args.touchpad, True):
      self._ui.Fail('Failed to enable touchpad.')

  def runTest(self):
    ui = self._ui
    ui.SetTitle(_MSG_TEST_TITLE)
    ui.AddButtons(_MSG_BUTTON_CAPTION)
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
    process = Spawn(['xinput', 'list-props', device], read_stdout=True,
                    log_stderr_on_error=True)
    if process.returncode != 0 or 'Device Enabled' not in process.stdout_data:
      return False

    process = Spawn(
      ['xinput', 'set-prop', device, 'Device Enabled', str(int(enabled))],
      read_stdout=True, log_stderr_on_error=True)
    return process.returncode == 0
