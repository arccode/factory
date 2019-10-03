# Copyright 2012 The Chromium OS Authors. All rights reserved.
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

  {
    "pytest_name": "line_check_item",
    "args": {
      "items": [
        ["i18n! Initialization", "lightbar init", false],
        ["i18n! Turn on lightbar", "lightbar enable", true],
        ["i18n! Clean up", "lightbar reset", false]
      ],
      "title": "i18n! LED Test"
    }
  }
"""

import collections
import subprocess

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test import session
from cros.factory.test import i18n
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg

CheckItem = collections.namedtuple('CheckItem',
                                   'instruction command judge_to_pass')


class LineCheckItemTest(test_case.TestCase):
  """Test a sequence of commands are successful or not.

  Properties:
    _items: A sequence of CheckItem.
  """
  ARGS = [
      i18n_arg_utils.I18nArg('title', 'test title.'),
      Arg('items', list,
          ('A sequence of items to check. Each item is a sequence: '
           ' [instruction, command, judge_to_pass].')),
      Arg('is_station', bool,
          ('Run the given commands on station (usually local host) instead of '
           'DUT, for example preparing connection configuration.'),
          default=False),
  ]

  def setUp(self):
    """Initializes _items"""
    self._dut = (device_utils.CreateStationInterface()
                 if self.args.is_station else
                 device_utils.CreateDUTInterface())
    self._items = []

    for item in self.args.items:
      if isinstance(item, list) and len(item) == 3:
        check_item = CheckItem(i18n.Translated(item[0], translate=False),
                               item[1], item[2])
      else:
        raise ValueError('Unknown item %r in args.items.' % item)
      self._items.append(check_item)

    if not any(item.judge_to_pass for item in self._items):
      raise ValueError('If judge_to_pass is not needed, use `exec_shell` test.')

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'checked_item', ['command', 'retcode', 'stdout', 'stderr'])
    testlog.UpdateParam('command', param_type=testlog.PARAM_TYPE.argument)

  def runTest(self):
    """Main entrance of the test."""
    self.ui.SetTitle(self.args.title)
    for item in self._items:
      command = item.command
      self.ui.SetState(item.instruction)

      process = self._dut.Popen(command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
      stdout, stderr = process.communicate()
      retcode = process.returncode
      event_log.Log('checked_item', command=command, retcode=retcode,
                    stdout=stdout, stderr=stderr)
      with self.group_checker:
        testlog.LogParam('command', command)
        testlog.LogParam('retcode', retcode)
        testlog.LogParam('stdout', stdout)
        testlog.LogParam('stderr', stderr)

      if retcode:
        session.console.info('%s: Exit code %d\nstdout: %s\nstderr: %s',
                             command, retcode, stdout, stderr)
        self.FailTask('%s: Exit code %d\nstdout: %s\nstderr: %s' %
                      (command, retcode, stdout, stderr))

      session.console.info('%s: stdout: %s\n', command, stdout)
      if stderr:
        session.console.info('stderr: %s', stderr)

      if item.judge_to_pass:
        self.ui.SetState(test_ui.PASS_FAIL_KEY_LABEL, append=True)
        key = self.ui.WaitKeysOnce([test_ui.ENTER_KEY, test_ui.ESCAPE_KEY])
        if key == test_ui.ESCAPE_KEY:
          self.FailTask('Judged as fail by operator.')
