# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to interactively check a sequence of shell commands on DUT.

Description
-----------
This test is very similar to ``exec_shell`` test, except that
``line_check_item`` has the ability to get operator confirmation no matter if
the shell command success or not.

If you simply want to run few commands (and fail if the return value is
non-zero), especially if you need to run commands on host or station, use
``exec_shell``.

If you simply want to run few commands and don't care if the commands success
or not, use ``exec_shell`` and add ``'|| true'`` for all commands.

If you are running some commands and some (at least one) commands need operator
to judge if that passed or not manually (for example checking if some LED has
lightened properly), use ``line_check_item``.

``line_check_item`` evaluates and executes the given ``items`` argument, where
each item is a sequence with 3 elements (instruction, command, judge_to_pass):

1. ``instruction``: A string passed to ``i18n.Translated`` to display on UI.
2. ``command``: A sequence or str as shell command to be passed to dut.Popen.
3. ``judge_to_pass``: A boolean value to indicate if these commands need user to
   judge pass or failure, even if the command returns zero (success).

Test Procedure
--------------
The test will go through each item and:

1. Display instruction on UI.
2. Execute command.
3. If judge_to_pass is True, wait for operator to confirm if passed or not.

Dependency
----------
The commands specified in items must be available on DUT.

Examples
--------
To turn on a 'lightbar' component and wait for confirmation, add this to test
list::

  OperatorTest(pytest_name='line_check_item',
               dargs={
                 'title': _('LED Test'),
                 'items': [
                   (_('Initialization'), 'lightbar init', False),
                   (_('Turn on lightbar'), 'lightbar enable', True),
                   (_('Clean up'), 'lightbar reset', False),
                 ]})
"""

import collections
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

CheckItem = collections.namedtuple('CheckItem',
                                   'instruction command judge_to_pass')


class LineCheckItemTest(unittest.TestCase):
  """Test a sequence of commands are successful or not.

  Properties:
    _ui: test ui.
    _template: test ui template.
    _items: A sequence of CheckItem.
    _current: current test item index in _items.
  """
  ARGS = [
      i18n_arg_utils.I18nArg('title', 'test title.'),
      Arg('items', (list, tuple),
          ('A sequence of items to check. Each item is a sequence of: '
           ' (instruction, command, judge_to_pass).'),
          optional=False),
      Arg('is_station', bool,
          ('Run the given commands on station (usually local host) instead of '
           'DUT, for example preparing connection configuration.'),
          default=False),
  ]

  def setUp(self):
    """Initializes _ui, _template, _current, and _items"""
    i18n_arg_utils.ParseArg(self, 'title')
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._current = 0
    self._dut = (device_utils.CreateStationInterface()
                 if self.args.is_station else
                 device_utils.CreateDUTInterface())
    self._items = []

    found_judge_to_pass = False
    for item in self.args.items:
      if isinstance(item, (list, tuple)) and len(item) == 3:
        check_item = CheckItem(i18n.Translated(item[0], translate=False),
                               item[1], item[2])
      else:
        raise ValueError('Unknown item %r in args.items.' % item)
      if item[2]:
        found_judge_to_pass = True
      self._items.append(check_item)

    if not found_judge_to_pass:
      raise ValueError('If judge_to_pass is not needed, use `exec_shell` test.')


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
