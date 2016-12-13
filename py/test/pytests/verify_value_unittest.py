#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for verify_value."""

import mock
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device.board import DeviceBoard as dut
from cros.factory.test import test_ui
from cros.factory.test.pytests import verify_value
from cros.factory.test.ui_templates import OneSection


class FakeArgs(object):
  def __init__(self, dargs):
    self.__dict__ = dargs


class VerifyValueTest(unittest.TestCase):
  # pylint: disable=protected-access

  def setUp(self):
    self._test = verify_value.VerifyValueTest()
    self._test._dut = mock.create_autospec(spec=dut)
    self._test._ui = mock.create_autospec(spec=test_ui.UI)
    self._test._template = mock.create_autospec(spec=OneSection)

  def testPass(self):
    item = [('command_compare_str', 'command_compare_str',
             'cat /xxx/xxx/xxx/fw_version', ['5566', 'abcd5566']),
            ('command_compare_number', 'command_compare_number',
             ['cat', '/sys/class/xxx/xxx'], [4, '5566', (0, 100)]),
            ('dut', 'dut', 'dut.info.cpu_count', 4),
            ('dut', 'dut', 'dut.info.cpu_count', (3, 5))]
    self._test._dut.CheckOutput.side_effect = ['abcd5566', '25\n']
    self._test._dut.info.cpu_count = 4
    self._test.args = FakeArgs({'items': item})
    self._test.runTest()

    calls = [mock.call(item[0][2]), mock.call(item[1][2])]

    self._test._dut.CheckOutput.assert_has_calls(calls)

  def testFail(self):
    item = [('command_compare_str', 'command_compare_str',
             'cat /xxx/xxx/xxx/fw_version', [5566, 'abcd5566'])]
    self._test._dut.CheckOutput.side_effect = ['25\n']
    self._test.args = FakeArgs({'items': item})

    self.assertRaises(AssertionError, self._test.runTest)


if __name__ == '__main__':
  unittest.main()
