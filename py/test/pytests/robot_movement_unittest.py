#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types
from cros.factory.test.fixture.robot.algorithm import Algorithm
from cros.factory.test.fixture.robot.robot import Robot
from cros.factory.test.pytests import robot_movement
from cros.factory.test import test_ui


class FakeArgs(object):
  def __init__(self, dargs):
    self.__dict__ = dargs


class RobotMovementTest(unittest.TestCase):
  # pylint: disable=protected-access

  Test = robot_movement.RobotMovement

  def setUp(self):
    self._test = self.Test()
    self._test._dut = mock.create_autospec(spec=types.DeviceInterface)
    self._test._dut.info.serial_number = 'SN123'
    self._test.ui_class = lambda event_loop: mock.Mock(spec=test_ui.StandardUI)
    self._test._robot = mock.create_autospec(spec=Robot)
    self._test._algorithm = mock.create_autospec(spec=Algorithm)
    self._test.args = FakeArgs({
        'positions': [0, 15, 16, 7, 10, 13, 14, 9, 8, 11, 12, 0],
        'period_between_movement': 0,
        'period_after_movement': 0,
        'result_dir': '/persist/data',
        'upload_to_server': False})

  def testSetUp(self):
    pass

  def testInitialize(self):
    self._test.Initialize()

    self._test._robot.Connect.assert_called_with()
    self._test._robot.SetMotor.assert_called_with(True)

  def testLoadDevice(self):
    self._test.ui.WaitKeysOnce = mock.Mock(spec=test_ui.StandardUI.WaitKeysOnce)

    self._test.LoadDevice()
    calls = [mock.call(False), mock.call(True)]
    self._test._robot.LoadDevice.assert_has_calls(calls)

  def testStartMoving(self):
    self._test.StartMoving()

    calls = [mock.call(position) for position in self._test.args.positions]
    self._test._robot.MoveTo.assert_has_calls(calls)

    self._test._robot.SetLED.assert_has_calls([
        mock.call(True), mock.call(False)])
    self._test._robot.LoadDevice.assert_called_with(False)
    self._test._robot.SetMotor.assert_called_with(False)
    self._test._robot.Disconnect.assert_called_with()
    self._test._algorithm.OnStartMoving.assert_called_with(self._test._dut)
    self._test._algorithm.OnStopMoving.assert_called_with(self._test._dut)

  def testCompute(self):
    self._test.Compute()

    self._test._algorithm.Compute.assert_called_with(self._test._dut)

  def testPushResult(self):
    self._test.PushResult()

    self._test._algorithm.PullResult.assert_called_with(self._test._dut)

  def testRunTest(self):
    self._test.Initialize = mock.Mock(spec=self._test.Initialize)
    self._test.LoadDevice = mock.Mock(spec=self._test.LoadDevice)
    self._test.StartMoving = mock.Mock(spec=self._test.StartMoving)
    self._test.Compute = mock.Mock(spec=self._test.Compute)
    self._test.PushResult = mock.Mock(spec=self._test.PushResult)

    self._test.runTest()

    self._test.Initialize.assert_called_with()
    self._test.LoadDevice.assert_called_with()
    self._test.StartMoving.assert_called_with()
    self._test.Compute.assert_called_with()
    self._test.PushResult.assert_called_with()


if __name__ == '__main__':
  unittest.main()
