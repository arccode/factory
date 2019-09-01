#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for SystemInterface and DeviceInterface in LinuxBoard."""

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device.boards import linux
from cros.factory.device import types


class MockProcess(object):
  def __init__(self, returncode):
    self._returncode = returncode

  def wait(self):
    return

  @property
  def returncode(self):
    return self._returncode


class LinuxTargetTest(unittest.TestCase):

  def setUp(self):
    self.link = types.DeviceLink()
    self.dut = linux.LinuxBoard(self.link)

  def testReadFile(self):
    self.link.Pull = mock.MagicMock(return_value='TEST')
    self.assertEquals(self.dut.ReadFile('/non-exist'), 'TEST')
    self.link.Pull.assert_called_with('/non-exist')

    self.dut.CheckOutput = mock.MagicMock(return_value='TEST')
    self.assertEquals(self.dut.ReadFile('/non-exist', 4), 'TEST')
    self.dut.CheckOutput.assert_called_with(['dd', 'bs=1', 'if=/non-exist',
                                             'count=4'])

    self.dut.CheckOutput = mock.MagicMock(return_value='TEST')
    self.assertEquals(self.dut.ReadFile('/non-exist', 4, 4), 'TEST')
    self.dut.CheckOutput.assert_called_with(['dd', 'bs=1', 'if=/non-exist',
                                             'count=4', 'skip=4'])

    self.dut.CheckOutput = mock.MagicMock(return_value='TEST')
    self.assertEquals(self.dut.ReadFile('/non-exist', skip=4), 'TEST')
    self.dut.CheckOutput.assert_called_with(['dd', 'bs=1', 'if=/non-exist',
                                             'skip=4'])

  def testWriteFile(self):
    def fakePush(local, remote):
      self.assertEquals(remote, '/non-exist')
      self.assertEquals(open(local).read(), 'TEST')

    self.link.Push = mock.MagicMock(side_effect=fakePush)
    self.dut.WriteFile('/non-exist', 'TEST')

  def testPopen(self):
    self.link.Shell = mock.MagicMock()
    self.assertEquals(self.dut.Popen(['ls']), self.link.Shell.return_value)
    self.link.Shell.assert_called_with(
        ['ls'], cwd=None, stdin=None, stdout=None, stderr=None)

    self.link.Shell = mock.MagicMock()
    self.assertEquals(self.dut.Popen('ls', cwd='/'),
                      self.link.Shell.return_value)
    self.link.Shell.assert_called_with(
        'ls', cwd='/', stdin=None, stdout=None, stderr=None)

  def testCall(self):
    self.link.Shell = mock.MagicMock(return_value=MockProcess(1))
    self.assertEquals(self.dut.Call(['ls']), 1)
    self.link.Shell.assert_called_with(
        ['ls'], cwd=None, stdin=None, stdout=None, stderr=None)

  def testCheckCall(self):
    self.link.Shell = mock.MagicMock(return_value=MockProcess(0))
    self.assertEquals(self.dut.CheckCall(['ls']), 0)
    self.link.Shell.assert_called_with(
        ['ls'], cwd=None, stdin=None, stdout=None, stderr=None)

    self.link.Shell = mock.MagicMock(return_value=MockProcess(1))
    with self.assertRaises(types.CalledProcessError):
      self.dut.CheckCall(['ls'])
    self.link.Shell.assert_called_with(
        ['ls'], cwd=None, stdin=None, stdout=None, stderr=None)

  def testCheckOutput(self):
    def fakeCallSuccess(command, cwd, stdin, stdout, stderr, log):
      # pylint: disable=unused-argument
      stdout.write('fake data')
      return 0
    def fakeCallFailure(command, cwd, stdin, stdout, stderr, log):
      # pylint: disable=unused-argument
      stdout.write('fake data')
      return 1
    self.dut.Call = mock.MagicMock(side_effect=fakeCallSuccess)
    self.assertEquals(self.dut.CheckOutput(['cmd']), 'fake data')
    self.dut.Call = mock.MagicMock(side_effect=fakeCallFailure)
    with self.assertRaises(types.CalledProcessError):
      self.dut.CheckOutput(['cmd'])

  def testCallOutput(self):
    def fakeCallSuccess(command, cwd, stdin, stdout, stderr, log):
      # pylint: disable=unused-argument
      stdout.write('fake data')
      return 0
    def fakeCallFailure(command, cwd, stdin, stdout, stderr, log):
      # pylint: disable=unused-argument
      stdout.write('fake data')
      return 1
    self.dut.Call = mock.MagicMock(side_effect=fakeCallSuccess)
    self.assertEquals(self.dut.CallOutput(['cmd']), 'fake data')
    self.dut.Call = mock.MagicMock(side_effect=fakeCallFailure)
    self.assertEquals(self.dut.CallOutput(['cmd']), None)

  def testGlob(self):
    self.dut.CallOutput = mock.MagicMock(return_value=None)
    self.assertEquals(self.dut.Glob('/non-exist'), [])
    self.dut.CallOutput = mock.MagicMock(return_value='/ab\n/a1b\n/a2b\n')
    self.assertEquals(self.dut.Glob('/a*b'), ['/ab', '/a1b', '/a2b'])

  @mock.patch('cros.factory.utils.sys_utils.GetVarLogMessagesBeforeReboot',
              return_value='var_log_msg')
  @mock.patch('cros.factory.utils.file_utils.TailFile', side_effect=IOError)
  @mock.patch('cros.factory.device.ec.EmbeddedController.GetECConsoleLog',
              return_value='ec_console_log_value')
  @mock.patch('cros.factory.device.ec.EmbeddedController.GetECPanicInfo',
              side_effect=IOError)
  def testGetStartupMessages(self, *unused_mocked_funcs):
    self.assertEquals(self.dut.GetStartupMessages(),
                      {'var_log_messages_before_reboot': 'var_log_msg',
                       'ec_console_log': 'ec_console_log_value'})


if __name__ == '__main__':
  unittest.main()
