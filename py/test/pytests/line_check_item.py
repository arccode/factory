# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to check a list of commands.

dargs:
  title_en: English test title.
  title_zh: Chinese test title.
  items: A list of tuple
      (instruction_en, instruction_zh, command, judge_to_pass).
      Each tuple represents an item to check.
      instruction_en: (str, unicode) instruction in English.
      instruction_zh: (str, unicode) instruction in Chinese.
      command: (list) commands to be passed to Spawn.
      judge_to_pass: (bool) require user to judge pass/fail even if
          command is successful.
"""

import unittest
from collections import namedtuple

from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import process_utils

CheckItem = namedtuple('CheckItem', 'instruction_en instruction_zh'
                                    ' command judge_to_pass')

class LineCheckItemTest(unittest.TestCase):
  """Test a list of commands are successful or not.
  Properties:
    _ui: test ui.
    _template: test ui template.
    _items: A list of CheckItems.
    _current: current test item index in _items.
  """
  ARGS = [
    Arg('title_en', (str, unicode), 'English test title.', optional=False),
    Arg('title_zh', (str, unicode), 'Chinese test title.', optional=False),
    Arg('items', list,
        ('A list of tuples, each representing an item to check.  Each tuple\n'
         'is of the format:\n'
         '\n'
         '  (instruction_en, instruction_zh, command, judge_to_pass)\n'
         '\n'
         'The fields are:\n'
         '\n'
         '- instruction_en: (str or unicode) instruction in English.\n'
         '- instruction_zh: (str or unicode) instruction in Chinese.\n'
         '- command: (list) commands to be passed to Spawn.\n'
         '- judge_to_pass: (bool) require user to judge pass/fail\n'
         '  even if command is successful.'),
        optional=False),
  ]

  def __init__(self, *args, **kwargs):
    """Initializes _ui, _template, _current, and _items"""
    super(LineCheckItemTest, self).__init__(*args, **kwargs)
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._items = []
    self._current = 0

  def NeedToJudgeSubTest(self):
    """Returns whether current subtest needs user to judege pass/fail or not."""
    return self._items[self._current].judge_to_pass

  def RunSubTest(self):
    """
    Runs current subtest and checks if command is successful.
    If current subtest needs to be judged, waits for user hitting Enter/Esc.
    If current subtest does not need to be judges, proceed to the next subtest.
    """
    inst_en = self._items[self._current].instruction_en
    inst_zh = self._items[self._current].instruction_zh
    command = self._items[self._current].command
    instruction = test_ui.MakeLabel(inst_en, inst_zh)
    if self.NeedToJudgeSubTest():
      instruction = instruction + '<br>' + test_ui.MakePassFailKeyLabel()
    self._template.SetState(instruction)

    process = process_utils.Spawn(command, read_stdout=True,
                                  log_stderr_on_error=True, shell=True)
    stdout, stderr = process.communicate()
    retcode = process.returncode
    Log('checked_item', command=command, retcode=retcode, stdout=stdout,
        stderr=stderr)

    if retcode:
      factory.console.info('%s: Exit code %d\nstdout: %s\nstderr: %s',
                           command, retcode, stdout, stderr)
      self._ui.Fail('%s: Exit code %d\nstdout: %s\nstderr: %s' %
                    (command, retcode, stdout, stderr))
    else:
      factory.console.info('%s: stdout: %s\n', command, stdout)
      if stderr:
        factory.console.info('stderr: %s', stderr)
      if not self.NeedToJudgeSubTest():
        self.PassSubTest()

  def RunNextSubTest(self):
    """Runs next subtest"""
    self._current = self._current + 1
    self.RunSubTest()

  def EnterKeyPressed(self, dummy_event):
    """
    Handler for enter key pressed by user. Passes the subtest if this subtest
    needs to be judged.
    """
    if self.NeedToJudgeSubTest():
      self.PassSubTest()

  def EscapeKeyPressed(self, dummy_event):
    """
    Handler for escape key pressed by user. Fails the subtest if this subtest
    needs to be judged.
    """
    if self.NeedToJudgeSubTest():
      self._ui.Fail('Judged as fail by operator.')

  def PassSubTest(self):
    """
    Passes the test if there is no test left, runs the next subtest otherwise.
    """
    if self._current + 1 == len(self.args.items):
      self._ui.Pass()
    else:
      self.RunNextSubTest()

  def runTest(self):
    """Main entrance of the test."""
    self._items = [CheckItem._make(item)  # pylint: disable=W0212
                       for item in self.args.items]
    self._template.SetTitle(test_ui.MakeLabel(self.args.title_en,
                                              self.args.title_zh))
    self._ui.BindKeyJS(test_ui.ENTER_KEY,
                       'test.sendTestEvent("enter_key_pressed", {});')
    self._ui.BindKeyJS(test_ui.ESCAPE_KEY,
                       'test.sendTestEvent("escape_key_pressed", {});')
    self._ui.AddEventHandler('enter_key_pressed', self.EnterKeyPressed)
    self._ui.AddEventHandler('escape_key_pressed', self.EscapeKeyPressed)
    self.RunSubTest()
    self._ui.Run()
