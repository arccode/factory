#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for DUTBoard helper functions."""

import mock
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut.link import DUTLink
from cros.factory.test.dut.board import DUTBoard
from cros.factory.test.dut.board import CalledProcessError

class BaseTargetTest(unittest.TestCase):

  def setUp(self):
    self.link = DUTLink()
    self.dut = DUTBoard(self.link)

  def testPath(self):
    # path should be POSIX.
    self.assertEquals('a/b', self.dut.path.join('a', 'b'))

  def testReadFile(self):
    self.link.Pull = mock.MagicMock(return_value='TEST')
    self.assertEquals(self.dut.ReadFile('/non-exist'), 'TEST')
    self.link.Pull.assert_called_with('/non-exist')

  def testWriteFile(self):
    def fakePush(local, remote):
      self.assertEquals(remote, '/non-exist')
      self.assertEquals(open(local).read(), 'TEST')

    self.link.Push = mock.MagicMock(side_effect=fakePush)
    self.dut.WriteFile('/non-exist', 'TEST')

  def testCall(self):
    self.link.Shell = mock.MagicMock(return_value=1)
    self.assertEquals(self.dut.Call(['ls']), 1)
    self.link.Shell.assert_called_with(['ls'], None, None, None)

  def testCheckCall(self):
    self.link.Shell = mock.MagicMock(return_value=0)
    self.assertEquals(self.dut.CheckCall(['ls']), 0)
    self.link.Shell.assert_called_with(['ls'], None, None, None)

    self.link.Shell = mock.MagicMock(side_effect=CalledProcessError(
        returncode=1, cmd='ls'))
    with self.assertRaises(CalledProcessError):
      self.dut.CheckCall(['ls'])
    self.link.Shell.assert_called_with(['ls'], None, None, None)

  def testCheckOutput(self):
    def fakeCallSuccess(command, stdin, stdout, stderr):
      stdout.write('fake data')
      return 0
    def fakeCallFailure(command, stdin, stdout, stderr):
      stdout.write('fake data')
      return 1
    self.dut.Call = mock.MagicMock(side_effect=fakeCallSuccess)
    self.assertEquals(self.dut.CheckOutput(['cmd']), 'fake data')
    self.dut.Call = mock.MagicMock(side_effect=fakeCallFailure)
    with self.assertRaises(CalledProcessError):
      self.dut.CheckOutput(['cmd'])

  def testCallOutput(self):
    def fakeCallSuccess(command, stdin, stdout, stderr):
      stdout.write('fake data')
      return 0
    def fakeCallFailure(command, stdin, stdout, stderr):
      stdout.write('fake data')
      return 1
    self.dut.Call = mock.MagicMock(side_effect=fakeCallSuccess)
    self.assertEquals(self.dut.CallOutput(['cmd']), 'fake data')
    self.dut.Call = mock.MagicMock(side_effect=fakeCallFailure)
    self.assertEquals(self.dut.CallOutput(['cmd']), None)

  def testFileExists(self):
    self.dut.Call = mock.MagicMock(return_value=0)
    self.assertEquals(self.dut.FileExists('/exists'), True)
    self.dut.Call.assert_called_with(['test', '-e', '/exists'])
    self.dut.Call = mock.MagicMock(return_value=1)
    self.assertEquals(self.dut.FileExists('/non-exist'), False)
    self.dut.Call.assert_called_with(['test', '-e', '/non-exist'])

  def testGlob(self):
    self.dut.CallOutput = mock.MagicMock(return_value=None)
    self.assertEquals(self.dut.Glob('/non-exist'), [])
    self.dut.CallOutput = mock.MagicMock(return_value='/ab\n/a1b\n/a2b\n')
    self.assertEquals(self.dut.Glob('/a*b'), ['/ab', '/a1b', '/a2b'])


if __name__ == '__main__':
  unittest.main()
