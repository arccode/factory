# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to check a list of commands.
"""

from collections import namedtuple
import subprocess
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test import i18n
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

CheckItem = namedtuple('CheckItem', 'instruction command judge_to_pass')


class LineCheckItemTest(unittest.TestCase):
  """Test a list of commands are successful or not.
  Properties:
    _ui: test ui.
    _template: test ui template.
    _items: A list of CheckItems.
    _current: current test item index in _items.
  """
  ARGS = i18n_arg_utils.BackwardCompatibleI18nArgs('title', 'test title.') + [
      Arg('items', list,
          ('A list of item to check. Each item can be either a simple string\n'
           'as shell command to execute, or a tuple in one of the formats:\n'
           '\n'
           '  (instruction, command, judge_to_pass)\n'
           '\n'
           '  (instruction_en, instruction_zh, command, judge_to_pass)\n'
           '\n'
           'The fields are:\n'
           '\n'
           '- instruction: instruction, would be passed to i18n.Translated.\n'
           '- instruction_en: (str or unicode) instruction in English.\n'
           '- instruction_zh: (str or unicode) instruction in Chinese.\n'
           '- command: (list or str) commands to be passed to Spawn.\n'
           '- judge_to_pass: (bool) require user to judge pass/fail\n'
           '  even if command is successful.'),
          optional=False),
      Arg('run_locally', bool, 'Run the given commands locally instead of DUT '
          '- for example doing configuration on Goofy host.', default=False),
      Arg('use_shell', bool, 'True to execute with shell=True.',
          default=True, optional=True),
      Arg('has_ui', bool, 'True if this test runs with goofy UI enabled.',
          optional=True, default=True)
  ]

  def setUp(self):
    """Initializes _ui, _template, _current, and _items"""
    i18n_arg_utils.ParseArg(self, 'title')
    self._ui = (test_ui.UI() if self.args.has_ui
                else test_ui.DummyUI(self))
    self._template = (ui_templates.OneSection(self._ui) if self.args.has_ui
                      else ui_templates.DummyTemplate())

    def _CommandToLabel(command, length=50):
      return (command[:length] + ' ...') if len(command) > length else command

    self._items = []
    for item in self.args.items:
      if isinstance(item, basestring):
        check_item = CheckItem(
            i18n.NoTranslation(_CommandToLabel(item)), item, False)
      elif isinstance(item, tuple) and len(item) == 4:
        # TODO(pihsun): This is to maintain backward compatibility. Should be
        #               removed after test lists are migrated to new format.
        check_item = CheckItem(
            i18n.Translated({'en-US': item[0], 'zh-CN': item[1]},
                            translate=False),
            item[2], item[3])
      elif isinstance(item, tuple) and len(item) == 3:
        check_item = CheckItem(
            i18n.Translated(item[0], translate=False), item[1], item[2])
      else:
        raise ValueError('Unknown item %r in args.items.' % item)
      self._items.append(check_item)

    self._current = 0
    self._dut = (None if self.args.run_locally else
                 device_utils.CreateDUTInterface())

  def NeedToJudgeSubTest(self):
    """Returns whether current subtest needs user to judge pass/fail or not."""
    return self._items[self._current].judge_to_pass

  def RunSubTest(self):
    """Runs current subtest and checks if command is successful.

    If current subtest needs to be judged, waits for user hitting
    Enter/Esc. If current subtest does not need to be judges, proceed to
    the next subtest.
    """
    inst = self._items[self._current].instruction
    command = self._items[self._current].command
    instruction = i18n_test_ui.MakeI18nLabel(inst)
    if self.NeedToJudgeSubTest():
      instruction = instruction + '<br>' + test_ui.MakePassFailKeyLabel()
    self._template.SetState(instruction)

    if self.args.run_locally:
      process = process_utils.Spawn(command, read_stdout=True,
                                    log_stderr_on_error=True,
                                    shell=self.args.use_shell)
    else:
      assert self.args.use_shell, (
          'DUT API does not support execution without shell')
      process = self._dut.Popen(command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    retcode = process.returncode
    event_log.Log('checked_item', command=command, retcode=retcode,
                  stdout=stdout, stderr=stderr)

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

  def EnterKeyPressed(self, event):
    """Handler for enter key pressed by user.

    Passes the subtest if this subtest needs to be judged.
    """
    del event  # Unused.
    if self.NeedToJudgeSubTest():
      self.PassSubTest()

  def EscapeKeyPressed(self, event):
    """Handler for escape key pressed by user.

    Fails the subtest if this subtest needs to be judged.
    """
    del event  # Unused.
    if self.NeedToJudgeSubTest():
      self._ui.Fail('Judged as fail by operator.')

  def PassSubTest(self):
    """Passes the test if there is no test left, runs the next subtest
    otherwise.
    """
    if self._current + 1 == len(self.args.items):
      self._ui.Pass()
    else:
      self.RunNextSubTest()

  def runTest(self):
    """Main entrance of the test."""
    self._template.SetTitle(i18n_test_ui.MakeI18nLabel(self.args.title))
    self._ui.BindKeyJS(test_ui.ENTER_KEY,
                       'test.sendTestEvent("enter_key_pressed", {});')
    self._ui.BindKeyJS(test_ui.ESCAPE_KEY,
                       'test.sendTestEvent("escape_key_pressed", {});')
    self._ui.AddEventHandler('enter_key_pressed', self.EnterKeyPressed)
    self._ui.AddEventHandler('escape_key_pressed', self.EscapeKeyPressed)
    self.RunSubTest()
    self._ui.Run()
