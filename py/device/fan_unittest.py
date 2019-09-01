#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for FanControl component."""

from __future__ import print_function

import os.path
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import fan
from cros.factory.device import types


class ECToolFanControlTest(unittest.TestCase):
  """Unittest for ECToolFanControl."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.fan = fan.ECToolFanControl(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetFanRPM(self):
    _MOCK_FAN_RPM = 'Fan 0 RPM: 2974\n'
    self.board.CallOutput(['ectool', 'pwmgetfanrpm']).AndReturn(_MOCK_FAN_RPM)
    self.mox.ReplayAll()
    self.assertEquals(self.fan.GetFanRPM(), [2974])
    self.mox.VerifyAll()

  def testSetFanRPM(self):
    self.board.CheckCall(['ectool', 'pwmsetfanrpm', '12345'])
    self.board.CheckCall(['ectool', 'pwmsetfanrpm', '1', '12345'])
    self.mox.ReplayAll()
    self.fan.SetFanRPM(12345)
    self.fan.SetFanRPM(12345, fan_id=1)
    self.mox.VerifyAll()

  def testSetFanRPMAuto(self):
    self.board.CheckCall(['ectool', 'autofanctrl'])
    self.board.CheckCall(['ectool', 'autofanctrl', '1'])
    self.mox.ReplayAll()
    self.fan.SetFanRPM(self.fan.AUTO)
    self.fan.SetFanRPM(self.fan.AUTO, fan_id=1)
    self.mox.VerifyAll()


class SysFSFanControlTest(unittest.TestCase):
  """Unittest for SysFSFanControl."""

  _FANS_INFO = [{'fan_id': None, 'path': '/sys/fan'}]

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.board.path = os.path

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetFanRPM(self):
    fan_obj = fan.SysFSFanControl(self.board, fans_info=self._FANS_INFO)
    self.board.ReadFile('/sys/fan/fan1_input').AndReturn('5566')
    self.mox.ReplayAll()
    self.assertEquals(fan_obj.GetFanRPM(), [5566])
    self.mox.VerifyAll()

  def testSetFanRPMAuto(self):
    fan_obj = fan.SysFSFanControl(self.board, fans_info=self._FANS_INFO)
    self.board.WriteFile('/sys/fan/pwm1_enable', '2')
    self.mox.ReplayAll()
    fan_obj.SetFanRPM(fan_obj.AUTO)
    self.mox.VerifyAll()

  def testSetFanRPM(self):
    fan_obj = fan.SysFSFanControl(self.board, fans_info=self._FANS_INFO)
    self.board.WriteFile('/sys/fan/pwm1_enable', '1')
    self.board.WriteFile('/sys/fan/pwm1', '5566')
    self.mox.ReplayAll()
    fan_obj.SetFanRPM(5566)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
