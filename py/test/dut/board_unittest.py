#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for DUTBoard helper functions."""

import mock
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import link
from cros.factory.test.dut.board import DUTBoard
from cros.factory.test.dut.board import CalledProcessError


class MockProcess(object):
  def __init__(self, returncode):
    self._returncode = returncode

  def wait(self):
    return

  @property
  def returncode(self):
    return self._returncode


class BaseTargetTest(unittest.TestCase):

  def setUp(self):
    self.link = link.DUTLink()
    self.dut = DUTBoard(self.link)

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

  def testCall(self):
    self.link.Shell = mock.MagicMock(return_value=MockProcess(1))
    self.assertEquals(self.dut.Call(['ls']), 1)
    self.link.Shell.assert_called_with(['ls'], None, None, None)

  def testCheckCall(self):
    self.link.Shell = mock.MagicMock(return_value=MockProcess(0))
    self.assertEquals(self.dut.CheckCall(['ls']), 0)
    self.link.Shell.assert_called_with(['ls'], None, None, None)

    self.link.Shell = mock.MagicMock(return_value=MockProcess(1))
    with self.assertRaises(CalledProcessError):
      self.dut.CheckCall(['ls'])
    self.link.Shell.assert_called_with(['ls'], None, None, None)

  def testCheckOutput(self):
    def fakeCallSuccess(command, stdin, stdout, stderr, log):
      stdout.write('fake data')
      return 0
    def fakeCallFailure(command, stdin, stdout, stderr, log):
      stdout.write('fake data')
      return 1
    self.dut.Call = mock.MagicMock(side_effect=fakeCallSuccess)
    self.assertEquals(self.dut.CheckOutput(['cmd']), 'fake data')
    self.dut.Call = mock.MagicMock(side_effect=fakeCallFailure)
    with self.assertRaises(CalledProcessError):
      self.dut.CheckOutput(['cmd'])

  def testCallOutput(self):
    def fakeCallSuccess(command, stdin, stdout, stderr, log):
      stdout.write('fake data')
      return 0
    def fakeCallFailure(command, stdin, stdout, stderr, log):
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


if __name__ == '__main__':
  unittest.main()
