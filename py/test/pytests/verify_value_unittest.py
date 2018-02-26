#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for verify_value."""

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types
from cros.factory.test.pytests import verify_value
from cros.factory.test import test_ui


class FakeArgs(object):
  def __init__(self, dargs):
    self.__dict__ = dargs


class VerifyValueTest(unittest.TestCase):
  # pylint: disable=protected-access

  def setUp(self):
    self._test = verify_value.VerifyValueTest()
    self._test._dut = mock.create_autospec(spec=types.DeviceInterface)
    self._test.ui_class = lambda event_loop: mock.create_autospec(
        spec=test_ui.StandardUI)

  def testPass(self):
    item = [['command_compare_str',
             'cat /xxx/xxx/xxx/fw_version', ['5566', 'abcd5566']],
            ['command_compare_number',
             ['cat', '/sys/class/xxx/xxx'], [4, '5566', [0, 100]]],
            ['dut', 'dut.info.cpu_count', 4],
            ['dut', 'dut.info.cpu_count', [[3, 5]]]]
    self._test._dut.CheckOutput.side_effect = ['abcd5566', '25\n']
    self._test._dut.info.cpu_count = 4
    self._test.args = FakeArgs({'items': item})
    self._test.runTest()

    calls = [mock.call(item[0][1]), mock.call(item[1][1])]

    self._test._dut.CheckOutput.assert_has_calls(calls)

  def testFail(self):
    item = [['command_compare_str',
             'cat /xxx/xxx/xxx/fw_version', [5566, 'abcd5566']]]
    self._test._dut.CheckOutput.side_effect = ['25\n']
    self._test.args = FakeArgs({'items': item})

    self.assertRaises(AssertionError, self._test.runTest)


if __name__ == '__main__':
  unittest.main()
