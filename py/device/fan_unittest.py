#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for FanControl component."""

import os.path
import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import fan


class ECToolFanControlTest(unittest.TestCase):
  """Unittest for ECToolFanControl."""

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.fan = fan.ECToolFanControl(self.board)

  def testGetFanRPM(self):
    _MOCK_FAN_RPM = 'Fan 0 RPM: 2974\n'
    self.board.CallOutput.return_value = _MOCK_FAN_RPM

    self.assertEqual(self.fan.GetFanRPM(), [2974])
    self.board.CallOutput.assert_called_once_with(['ectool', 'pwmgetfanrpm'])

  def testSetFanRPM(self):
    self.fan.SetFanRPM(12345)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'pwmsetfanrpm', '12345'])

    self.fan.SetFanRPM(12345, fan_id=1)
    self.board.CheckCall.assert_called_with(
        ['ectool', 'pwmsetfanrpm', '1', '12345'])

  def testSetFanRPMAuto(self):
    self.fan.SetFanRPM(self.fan.AUTO)
    self.board.CheckCall.assert_called_with(['ectool', 'autofanctrl'])

    self.fan.SetFanRPM(self.fan.AUTO, fan_id=1)
    self.board.CheckCall.assert_called_with(['ectool', 'autofanctrl', '1'])


class SysFSFanControlTest(unittest.TestCase):
  """Unittest for SysFSFanControl."""

  _FANS_INFO = [{'fan_id': None, 'path': '/sys/fan'}]

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.board.path = os.path

  def testGetFanRPM(self):
    fan_obj = fan.SysFSFanControl(self.board, fans_info=self._FANS_INFO)
    self.board.ReadFile.return_value = '5566'

    self.assertEqual(fan_obj.GetFanRPM(), [5566])
    self.board.ReadFile.assert_called_once_with('/sys/fan/fan1_input')

  def testSetFanRPMAuto(self):
    fan_obj = fan.SysFSFanControl(self.board, fans_info=self._FANS_INFO)

    fan_obj.SetFanRPM(fan_obj.AUTO)
    self.board.WriteFile.assert_called_once_with('/sys/fan/pwm1_enable', '2')

  def testSetFanRPM(self):
    fan_obj = fan.SysFSFanControl(self.board, fans_info=self._FANS_INFO)
    write_file_calls = [
        mock.call('/sys/fan/pwm1_enable', '1'),
        mock.call('/sys/fan/pwm1', '5566')]

    fan_obj.SetFanRPM(5566)
    self.assertEqual(self.board.WriteFile.call_args_list, write_file_calls)


if __name__ == '__main__':
  unittest.main()
