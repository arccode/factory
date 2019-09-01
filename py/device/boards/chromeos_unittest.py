#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for DeviceInterface in LinuxBoard."""

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device.boards import chromeos
from cros.factory.device import types


class ChromeOSBoardTest(unittest.TestCase):

  def setUp(self):
    self.link = types.DeviceLink()
    self.dut = chromeos.ChromeOSBoard(self.link)

  @mock.patch('cros.factory.device.boards.chromeos.ChromeOSBoard.CallOutput',
              return_value='mosys_log_value')
  @mock.patch(
      'cros.factory.device.boards.linux.LinuxBoard.GetStartupMessages',
      return_value={'aaa': 'bbb'})
  def testGetStartupMessages(self, *unused_mocked_funcs):
    self.assertEquals(self.dut.GetStartupMessages(),
                      {'aaa': 'bbb', 'mosys_log': 'mosys_log_value'})


if __name__ == '__main__':
  unittest.main()
