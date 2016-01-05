#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import board
from cros.factory.test.dut import path


class PathTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.Mock(spec=board.DUTBoard)
    self.path = path.Path(self.dut)

  def testExists(self):
    self.dut.Call = mock.MagicMock(return_value=0)
    self.assertEquals(self.path.exists('/exists'), True)
    self.dut.Call.assert_called_with(['test', '-e', '/exists'])
    self.dut.Call = mock.MagicMock(return_value=1)
    self.assertEquals(self.path.exists('/non-exist'), False)
    self.dut.Call.assert_called_with(['test', '-e', '/non-exist'])

  def testIsDir(self):
    self.dut.Call = mock.MagicMock(return_value=0)
    self.assertEquals(self.path.isdir('/a/dir'), True)
    self.dut.Call.assert_called_with(['test', '-d', '/a/dir'])
    self.dut.Call = mock.MagicMock(return_value=1)
    self.assertEquals(self.path.isdir('/not/dir'), False)
    self.dut.Call.assert_called_with(['test', '-d', '/not/dir'])

  def testRealpath(self):
    self.dut.CallOutput = mock.MagicMock(return_value='/the/real/path\n')
    self.assertEquals(self.path.realpath('/some/other/path'), '/the/real/path')
    self.dut.CallOutput.assert_called_with(
        ['realpath', '-m', '/some/other/path'])


class AndroidPathTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.Mock(spec=board.DUTBoard)
    self.path = path.AndroidPath(self.dut)

  def testRealPathWithDoubleSlash(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/')
    self.assertEquals(self.path.realpath('///'), '/')
    self.dut.CheckOutput.assert_called_with(
        ['realpath', '/'])

  def testRealPathWithDoubleDot(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/')
    self.dut.CallOutput = mock.MagicMock(return_value='/')
    self.assertEquals(self.path.realpath('/..'), '/')
    self.dut.CheckOutput.assert_called_with(
        ['realpath', '/'])
    self.dut.CallOutput.assert_called_with(
        ['realpath', '/..'])

  def testRealPathWhenCannotResolveSymbolicLink(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/')
    self.dut.CallOutput = mock.MagicMock(side_effect=['/a', None])
    self.assertEquals(self.path.realpath('/a/xx/b/c/../d/e'), '/a/xx/b/d/e')
    self.dut.CheckOutput.assert_called_with(
        ['realpath', '/'])
    self.assertEquals(self.dut.CallOutput.mock_calls,
                      [mock.call(['realpath', '/a']),
                       mock.call(['realpath', '/a/xx'])])


if __name__ == '__main__':
  unittest.main()
