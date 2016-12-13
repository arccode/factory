# -*- coding: utf-8 -*-
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test to verify value of the given command."""

from collections import namedtuple
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


Item = namedtuple('CheckItem', 'name_en name_zh command expected_value')


class VerifyValueTest(unittest.TestCase):
  ARGS = [
      Arg('items', list,
          'A list of tuples, each representing an item to check. Each tuple\n'
          'is of the format:\n'
          '\n'
          '  (name_en, name_zh, command/func_name, expected_value)\n'
          '\n'
          'The fields are:\n'
          '    - name_en: (str or unicode) name of the check in English.\n'
          '    - name_zh: (str or unicode) name of the check in Chinese.\n'
          '    - command/func_name: (str or list) Can be one of the following:\n'
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
      item = Item._make(item)
      name = test_ui.MakeLabel(item.name_en, item.name_zh)
      self._template.SetState(name)
      command = item.command

      factory.console.info('Try to get value from: %s', command)
      logging.info('Get value from: %s', command)
      if isinstance(command, str) and command.startswith('dut.'):
        value = eval('self._dut.%s' % command[4:])  # pylint: disable=eval-used
      else:
        value = self._dut.CheckOutput(command)
      value_str = str(value).strip()
      factory.console.info('%s', value_str)

      expected_values = (item.expected_value
                         if isinstance(item.expected_value, list)
                         else [item.expected_value])

      match = False
      for expected_value in expected_values:
        if isinstance(expected_value, tuple):
          v = float(value_str)
          match = expected_value[0] <= v <= expected_value[1]
        elif isinstance(expected_value, int):
          match = expected_value == int(value_str)
        else:
          match = expected_value == value_str
        if match:
          break

      if not match:
        self.fail('%s is not in %s' % (value_str, str(item.expected_value)))
