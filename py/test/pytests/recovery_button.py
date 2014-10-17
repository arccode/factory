# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a recovery button test."""

import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.process_utils import SpawnOutput

_MSG_PRESS_SPACE = test_ui.MakeLabel(
    'Hit SPACE to start test...',
    zh=u'按 "空白键" 开始测试...',
    css_class='recovery-button-info')

_MSG_RECOVERY_BUTTON_TEST = lambda s, t: test_ui.MakeLabel(
    'Please press recovery button for %.1f seconds (%d seconds remaining).' %
        (s, t),
    zh=u'请持续按压恢复按钮 %.1f 秒 (剩余时间: %d 秒).' % (s, t),
    css_class='recovery-button-info')

_HTML_RECOVERY_BUTTON = """
<table style="width: 70%; margin: auto;">
  <tr>
    <td align="center"><div id="recovery_button_title"></div></td>
  </tr>
</table>
"""

_CSS_RECOVERY_BUTTON = """
  .recovery-button-info { font-size: 2em; }
"""

_JS_SPACE = """
window.onkeydown = function(event) {
  if (event.keyCode == " ".charCodeAt(0))
    test.sendTestEvent("StartTest", '');
}
"""


class RecoveryButtonTest(unittest.TestCase):
  """Tests Recovery Button."""
  ARGS = [
    Arg('timeout_secs', int, 'Timeout to press recovery button.', default=10),
    Arg('polling_interval_secs', float,
        'Interval between checking whether recovery buttion is pressed or not.'
        'Valid values: 0.2, 0.5 and 1.0',
        default=0.5),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_RECOVERY_BUTTON)
    self.template.SetState(_HTML_RECOVERY_BUTTON)
    self.ui.RunJS(_JS_SPACE)
    self.ui.SetHTML(_MSG_PRESS_SPACE, id='recovery_button_title')
    self.ui.AddEventHandler('StartTest', self.StartTest)
    if self.args.polling_interval_secs not in (0.2, 0.5, 1.0):
      raise ValueError('The value of polling_interval_secs is invalid: %f' %
          self.args.polling_interval_secs)

  def StartTest(self, _):
    polling_iterations_per_second = int(1 / self.args.polling_interval_secs)
    for i in xrange(self.args.timeout_secs):
      self.ui.SetHTML(_MSG_RECOVERY_BUTTON_TEST(
                          self.args.polling_interval_secs,
                          self.args.timeout_secs - i),
                      id='recovery_button_title')
      for _ in xrange(polling_iterations_per_second):
        time.sleep(self.args.polling_interval_secs)
        if '1' == SpawnOutput(['crossystem', 'recoverysw_cur'], log=True):
          self.ui.Pass()
          return

    self.ui.Fail('Recovery button test failed.')

  def runTest(self):
    self.ui.Run()
