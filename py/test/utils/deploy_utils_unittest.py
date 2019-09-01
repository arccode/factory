#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device.boards import chromeos
from cros.factory.device import types
from cros.factory.test.utils import deploy_utils

# pylint: disable=protected-access
class FactoryPythonArchiveUnittest(unittest.TestCase):
  def setUp(self):
    self.link = mock.Mock(spec=types.DeviceLink)
    self.dut = chromeos.ChromeOSBoard(self.link)
    self.remote_factory_root = '/remote/factory/root'
    self.dut.storage.GetFactoryRoot = mock.MagicMock(
        return_value=self.remote_factory_root)

    self.remote_factory_par = '/remote/factory/root/factory.par'
    self.local_factory_par = '/path/to/factory.par'

    self.factory_par = deploy_utils.FactoryPythonArchive(
        self.dut, self.local_factory_par)

  def _testCallWithString(self, is_local):
    self.link.IsLocal = mock.MagicMock(return_value=is_local)
    command = 'fake_command arg1 arg2'
    expected_call = ('sh ' + self.factory_par.remote_factory_par +
                     ' fake_command arg1 arg2')
    return_value = 'fake_return_value'
    self.dut.Call = mock.MagicMock(return_value=return_value)
    self.factory_par.PushFactoryPar = mock.MagicMock()

    result = self.factory_par.Call(command)

    self.dut.Call.assert_called_with(expected_call)
    self.assertEquals(return_value, result)
    self.factory_par.PushFactoryPar.assert_called_with()

  def testCallWithString(self):
    self._testCallWithString(True)
    self._testCallWithString(False)

  def _testCallWithList(self, is_local):
    self.link.IsLocal = mock.MagicMock(return_value=is_local)
    command = ['fake_command', 'arg1', 'arg2']
    expected_call = ['sh', self.factory_par.remote_factory_par, 'fake_command',
                     'arg1', 'arg2']
    return_value = 'fake_return_value'
    self.dut.Call = mock.MagicMock(return_value=return_value)
    self.factory_par.PushFactoryPar = mock.MagicMock()

    result = self.factory_par.Call(command)

    self.dut.Call.assert_called_with(expected_call)
    self.assertEquals(return_value, result)
    self.factory_par.PushFactoryPar.assert_called_with()

  def testCallWithList(self):
    self._testCallWithList(True)
    self._testCallWithList(False)

  def testPushFactoryParChecksumMatched(self):
    self.link.IsLocal = mock.MagicMock(return_value=False)
    types.DeviceProperty.Override(
        self.factory_par, 'checksum', 'checksum_value')
    self.dut.CheckOutput = mock.MagicMock(return_value='checksum_value')

    self.factory_par.PushFactoryPar()
    self.dut.link.Push.assert_not_called()

  def testPushFactoryParChecksumNotMatched(self):
    self.link.IsLocal = mock.MagicMock(return_value=False)
    types.DeviceProperty.Override(
        self.factory_par, 'checksum', 'checksum_value')
    self.dut.CheckCall = mock.MagicMock(return_value='checksum_value~')

    self.factory_par.PushFactoryPar()

    self.dut.link.Push.assert_called_with(self.local_factory_par,
                                          self.remote_factory_par)


if __name__ == '__main__':
  unittest.main()
