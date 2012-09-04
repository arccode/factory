# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test generic pointing device."""

from string import Template  # pylint: disable=W0402
import unittest

from cros.factory.test import test_ui
from cros.factory.test import ui_templates

_MSG_TEST_TITLE = test_ui.MakeLabel('Pointing Device Test',
                                    u'指向装置测试')
_MSG_INSTRUCTION = test_ui.MakeLabel(
  'Please use a pointing device to click the four corner buttons.',
  u'请使用指向装置点击角落的四个按钮')
_MSG_BUTTON_CAPTION = test_ui.MakeLabel('Click me', u'点击')

_CSS = """
.pd-button-div { font-size: 24px; position: absolute; text-align: center; }
.pd-button { height: 40px; width: 150px; }
#pd-button-tl { top: 30px; left: 30px; }
#pd-button-tr { top: 30px; right: 30px; }
#pd-button-bl { bottom: 30px; left: 30px; }
#pd-button-br { bottom: 30px; right: 30px; }
.instruction { font-size: 24px; padding-bottom: 12px; }
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

_INSTRUCTION_HTML = '<div class="instruction">%s</div>' % _MSG_INSTRUCTION

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
    window.test.pass();
  }
};
"""

class PointingDeviceUI(ui_templates.OneSection):
  """Composes an UI for pointing device test.
  """

  def __init__(self, ui):
    super(PointingDeviceUI, self).__init__(ui)
    self._ui.AppendCSS(_CSS)
    self._ui.RunJS(_JS)

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


class PointingDeviceTest(unittest.TestCase):
  """Generic pointing device test.

  It draws four buttons and the test will pass after four buttons are clicked.
  """
  ARGS = []

  def __init__(self, *args, **kwargs):
    super(PointingDeviceTest, self).__init__(*args, **kwargs)
    self._ui = PointingDeviceUI(test_ui.UI())

  def runTest(self):
    ui = self._ui
    ui.SetTitle(_MSG_TEST_TITLE)
    ui.AddButtons(_MSG_BUTTON_CAPTION)
    ui.AppendHTML(_INSTRUCTION_HTML)
    ui.BindStandardKeys(bind_pass_key=False, bind_fail_key=True)
    ui.Run()
