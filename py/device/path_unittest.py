#!/usr/bin/env python3
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import path


class PathTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.Mock(spec=device_types.DeviceInterface)
    self.path = path.Path(self.dut)

  def testExists(self):
    self.dut.Call = mock.MagicMock(return_value=0)
    self.assertEqual(self.path.exists('/exists'), True)
    self.dut.Call.assert_called_with(['test', '-e', '/exists'])
    self.dut.Call = mock.MagicMock(return_value=1)
    self.assertEqual(self.path.exists('/non-exist'), False)
    self.dut.Call.assert_called_with(['test', '-e', '/non-exist'])

  def testIsDir(self):
    self.dut.Call = mock.MagicMock(return_value=0)
    self.assertEqual(self.path.isdir('/a/dir'), True)
    self.dut.Call.assert_called_with(['test', '-d', '/a/dir'])
    self.dut.Call = mock.MagicMock(return_value=1)
    self.assertEqual(self.path.isdir('/not/dir'), False)
    self.dut.Call.assert_called_with(['test', '-d', '/not/dir'])

  def testRealpath(self):
    self.dut.CallOutput = mock.MagicMock(return_value='/the/real/path\n')
    self.assertEqual(self.path.realpath('/some/other/path'), '/the/real/path')
    self.dut.CallOutput.assert_called_with(
        ['realpath', '-m', '/some/other/path'])


class AndroidPathTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.Mock(spec=device_types.DeviceInterface)
    self.path = path.AndroidPath(self.dut)

  def testQuickReturn(self):
    self.dut.CallOutput = mock.MagicMock(return_value='/abc/')
    self.assertEqual(self.path.realpath('/def/'), '/abc/')
    self.dut.CallOutput.assert_called_with(['realpath', '/def/'])

  def testRealPathWithDoubleSlash(self):
    self.dut.CallOutput = mock.MagicMock(return_value=None)
    self.dut.CheckOutput = mock.MagicMock(return_value='/')
    self.assertEqual(self.path.realpath('///'), '/')
    self.dut.CheckOutput.assert_called_with(
        ['realpath', '/'])

  def testRealPathWithDoubleDot(self):
    self.dut.CallOutput = mock.MagicMock(side_effect=[None])
    self.dut.CheckOutput = mock.MagicMock(return_value='/')
    self.assertEqual(self.path.realpath('/..'), '/')
    self.dut.CheckOutput.assert_called_with(['realpath', '/'])

  def testRealPathWhenCannotResolveSymbolicLink(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/')
    self.dut.CallOutput = mock.MagicMock(side_effect=[None, '/a', None])
    self.assertEqual(self.path.realpath('/a/xx/b/c/../d/e'), '/a/xx/b/d/e')
    self.dut.CheckOutput.assert_called_with(
        ['realpath', '/'])
    self.assertEqual(self.dut.CallOutput.mock_calls,
                     [mock.call(['realpath', '/a/xx/b/c/../d/e']),
                      mock.call(['realpath', '/a']),
                      mock.call(['realpath', '/a/xx'])])


if __name__ == '__main__':
  unittest.main()
