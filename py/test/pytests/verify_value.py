# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to verify value of the given command.

Description
-----------
This test evaluates and executes the given `items` argument, where
each item is a sequence with 3 elements (name, command, expected_value):

1. `name`: A string passed to `i18n.Translated` to display on UI.
2. `command`: Can be one of:

  * A sequence or str as shell command to be passed to `dut.Popen`. Leading
    and trailing whitespace of the output would be stripped.
  * A str starts with `dut.`, which would be transformed into corresponding
    device API call. e.g. `dut.info.cpu_count`.

3. `expected_value`: A list of possible expected value of output of command,
   each item can be one of:

  * The expected str or int of output.
  * A range `[min_value, max_value]`, indicate that the output value should be
    within the range.

  If `expected_value` only contains a single item of type str or int, the
  item can be used as `expected_value` directly.

This test will check the output of shell commands given from argument `items`
one by one, and fail if any command have non-zero return value or have output
that doesn't match any of the expected values.

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and it will run the shell commands or execute the device API
specified, one by one; and fail if any of the command doesn't match the
expected values.

Dependency
----------
The test uses system shell to execute commands, which may be different per
platform. Also, the command may be not always available on target system.
You have to review each command to check if that's provided on DUT.

Examples
--------
To check if the ec version match some value, add this in test list::

  {
    "pytest_name": "verify_value",
    "args": {
      "items": ["i18n! EC Version", "dut.info.ec_version", "board_v1.0.1234"]
    }
  }

To check if the cpu0 mode is in powersave mode::

  {
    "pytest_name": "verify_value",
    "args": {
      "items": [
        "i18n! CPU speed",
        "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor",
        "powersave"
      ]
    }
  }
"""

from collections import namedtuple
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test import i18n
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


Item = namedtuple('CheckItem', 'name command expected_value')


class VerifyValueTest(unittest.TestCase):
  ARGS = [
      Arg('items', list,
          'A list of sequences, each representing an item to check.\n'
          'Each sequence is in format:\n'
          '\n'
          '  (name, command/func_name, expected_value)\n'
          '\n'
          'The fields are:\n'
          '    - name: name of the check, would be passed to i18n.Translated.\n'
          '    - command/func_name: (str or list) one of the following:\n'
          '        - A command (str or list) that returns a value.\n'
          "            E.g. 'cat /sys/class/xxx/xxx/xxx'\n"
          "        - A DUT fucntion (str) to be called, begin with 'dut.'.\n"
          "            E.g. 'dut.info.cpu_count', 'dut.storage.GetDatRoot()'\n"
          '    - expected_value: (str, int, tuples of two number, or a list).\n'
          '        - Can be one of the following:\n'
          '            - An expected str\n'
          '            - An expected int\n'
          '            - (min_value, max_value)\n'
          '            - A list of all possible values, each item can be one\n'
          '                of the above types.'),
      Arg('has_ui', bool, 'True if this test runs with goofy UI enabled.',
          optional=True, default=True)
      ]

  def setUp(self):
    self._ui = test_ui.UI() if self.args.has_ui else test_ui.DummyUI(self)
    self._template = (ui_templates.OneSection(self._ui) if self.args.has_ui
                      else ui_templates.DummyTemplate())
    self._dut = device_utils.CreateDUTInterface()

  def runTest(self):
    for item in self.args.items:
      item = Item(i18n.Translated(item[0], translate=False), item[1], item[2])
      name = i18n_test_ui.MakeI18nLabel(item.name)
      self._template.SetState(name)
      command = item.command

      session.console.info('Try to get value from: %s', command)
      logging.info('Get value from: %s', command)
      if isinstance(command, str) and command.startswith('dut.'):
        value = eval('self._dut.%s' % command[4:])  # pylint: disable=eval-used
      else:
        value = self._dut.CheckOutput(command)
      value_str = str(value).strip()
      session.console.info('%s', value_str)

      expected_values = (item.expected_value
                         if isinstance(item.expected_value, list)
                         else [item.expected_value])

      match = False
      for expected_value in expected_values:
        if isinstance(expected_value, (list, tuple)):
          v = float(value_str)
          match = expected_value[0] <= v <= expected_value[1]
        elif isinstance(expected_value, int):
          match = expected_value == int(value_str)
        else:
          match = expected_value == value_str
        if match:
          break

      if not match:
        self.fail('%s is not in %s' % (value_str, item.expected_value))
