#!/usr/bin/python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import board
from cros.factory.test.dut import link
from cros.factory.test.utils import deploy_utils

# pylint: disable=W0212
class FactoryPythonArchiveUnittest(unittest.TestCase):
  def setUp(self):
    self.dut = mock.Mock(spec=board.DUTBoard)
    self.dut.link = mock.Mock(spec=link.DUTLink)
    self.factory_par = deploy_utils.FactoryPythonArchive(self.dut)
    self.factory_par_path = deploy_utils.FactoryPythonArchive.FACTORY_PAR_PATH

  def testCallWithString(self):
    command = 'fake_command arg1 arg2'
    expected_call = self.factory_par_path + ' fake_command arg1 arg2'
    return_value = 'fake_return_value'
    self.dut.Call = mock.MagicMock(return_value=return_value)

    result = self.factory_par.Call(command)

    self.dut.Call.assert_called_with(expected_call)
    self.assertEquals(return_value, result)

  def testCallWithList(self):
    command = ['fake_command', 'arg1', 'arg2']
    expected_call = [self.factory_par_path, 'fake_command', 'arg1', 'arg2']
    return_value = 'fake_return_value'
    self.dut.Call = mock.MagicMock(return_value=return_value)

    result = self.factory_par.Call(command)

    self.dut.Call.assert_called_with(expected_call)
    self.assertEquals(return_value, result)


if __name__ == '__main__':
  unittest.main()
