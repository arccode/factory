# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''This is a factory test to test keyboard backlight.'''

import unittest

from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import process_utils


_TEST_TITLE = test_ui.MakeLabel('Keyboard Backlight Test', u'鍵盤背光測試')

_SUBTESTS = (('lights up', u'亮起', '100'),
             ('is off', u'熄滅', '0'))

_INSTRUCTION_EN = 'If the keyboard backlight %s, press ENTER. '
_INSTRUCTION_ZH = u'檢查鍵盤背光是否%s，是請按ENTER。'

class KeyboardBacklightTest(unittest.TestCase):

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._current = 0

  def NextSubTest(self):
    inst_en = _INSTRUCTION_EN % _SUBTESTS[self._current][0]
    inst_zh = _INSTRUCTION_ZH % _SUBTESTS[self._current][1]
    instruction = (test_ui.MakeLabel(inst_en, inst_zh) +
                   test_ui.MakePassFailKeyLabel(pass_key=False))
    self._template.SetState(instruction)
    process_utils.Spawn(['ectool', 'pwmsetkblight',
                         _SUBTESTS[self._current][2]], ignore_stdout=True,
                         log_stderr_on_error=True, check_call=True)
    self._current = self._current + 1

  def PassSubtest(self, dummy_event):
    if self._current == len(_SUBTESTS):
      self._ui.Pass()
    else:
      self.NextSubTest()
    return True

  def runTest(self):
    '''Main entrance of keyboard backlight test.'''
    self._template.SetTitle(_TEST_TITLE)
    self._ui.BindKeyJS(test_ui.ENTER_KEY,
                       'test.sendTestEvent("pass_subtest", {});')
    self._ui.BindStandardKeys(bind_pass_keys=False)
    self._ui.AddEventHandler('pass_subtest', self.PassSubtest)
    self.NextSubTest()
    self._ui.Run()
