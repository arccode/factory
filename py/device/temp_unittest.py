#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for temporary files module dut.temp."""

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import temp as temp_module

class TemporaryFilesTest(unittest.TestCase):

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.temp = temp_module.TemporaryFiles(self.dut)
    self.android_temp = temp_module.AndroidTemporaryFiles(self.dut)

  def testMkfile(self):
    template = 'cftmp.XXXXXX'
    result = '/tmp/abcdef'
    temp = self.temp

    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(False))
    self.dut.CheckOutput.assert_called_with(['mktemp', '--tmpdir', template])

    # test is_dir
    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(True))
    self.dut.CheckOutput.assert_called_with(
        ['mktemp', '-d', '--tmpdir', template])
    # test dir
    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(False, dir='/local'))
    self.dut.CheckOutput.assert_called_with(
        ['mktemp', '--tmpdir=/local', template])

    # test suffix
    result = '/tmp/abcdef.ext'
    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(False, suffix='.ext'))
    self.dut.CheckOutput.assert_called_with(
        ['mktemp', '--tmpdir', template + '.ext'])

    # test prefix
    template = 'pre.XXXXXX'
    result = '/tmp/pre_abcdef'
    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(False, prefix='pre'))
    self.dut.CheckOutput.assert_called_with(['mktemp', '--tmpdir', template])

  def testAndroidTemp(self):
    temp = self.android_temp
    template = 'cftmp.XXXXXX'
    result = '/tmp/abcdef'

    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(False))
    self.dut.CheckOutput.assert_called_with(['mktemp', template])

    # test dir
    self.dut.CheckOutput = mock.MagicMock(return_value=result)
    self.assertEquals(result, temp.mktemp(False, dir='/local'))
    self.dut.CheckOutput.assert_called_with(
        ['mktemp', '-p', '/local', template])



if __name__ == '__main__':
  unittest.main()
