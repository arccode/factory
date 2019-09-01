#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import action_function


class ActionFunctionTest(unittest.TestCase):
  def setUp(self):
    self.func = action_function.ActionFunction()

  def testCall(self):
    self.func.Action = mock.MagicMock(return_value=True)
    ret = self.func(function.INITIAL_DATA)
    self.func.Action.assert_called_once_with()
    self.assertEquals(ret, function.INITIAL_DATA)

  def testNotCall(self):
    self.func.Action = mock.MagicMock(return_value=True)
    ret = self.func(function.NOTHING)
    self.func.Action.assert_not_called()
    self.assertEquals(ret, function.NOTHING)

  def testCallFail(self):
    self.func.Action = mock.MagicMock(return_value=False)
    ret = self.func([{}])
    self.func.Action.assert_called_once_with()
    self.assertEquals(ret, function.NOTHING)


if __name__ == '__main__':
  unittest.main()
