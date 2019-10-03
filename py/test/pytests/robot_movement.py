# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Control a robot to move a device for testing specific sensors.

Description
-----------
This test controls a robot (arm) to move a device along a predefined
trajectory, to verify the functionalities of the sensors on the device.

Test Procedure
--------------
1. Robot is moved to the unloaded position.
2. Ask the operator to mount the device.
3. Robot is moved to the loaded position.
4. Robot is moved by the given trajectory.
5. Robot is moved to the unloaded position.
6. Verify the data from sensors on the device.
7. Ask the operator to unmount the device.

Dependency
----------
Depend on the class specified by the arguments `robot_fixture` and
`algorithm` to move the robot, get result from the device, and
verify the result.

Examples
--------
To use `robot.foo` to control the robot fixture, and use `algo.bar` to
calculate and verify the sensor data, add this in test list::

  {
    "pytest_name": "robot_movement",
    "args": {
      "positions": [0, 1, 2, 3, 4, 5],
      "robot_fixture": "robot.foo",
      "algorithm": "algo.bar"
    }
  }

One can also pass parameters to the classes specified in `robot_fixture` and
`algorithm`::

  {
    "pytest_name": "robot_movement",
    "args": {
      "positions": [0, 1, 2, 3, 4, 5],
      "robot_fixture": "robot.foo",
      "robot_fixture_args": {
        "speed": 30
      },
      "algorithm_args": {
        "trajectory_id": "bar1"
      },
      "algorithm": "algo.bar"
    }
  }

"""

import logging

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.fixture import utils as fixture_utils
from cros.factory.test.i18n import _
from cros.factory.test import server_proxy
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class RobotMovement(test_case.TestCase):
  """A general task that use a robot to move the device.

  Two detail implementations are required for this task. One is the fixture for
  controlling the robot, and the other is the algorithm for computation.

  The process of this task is as following:
  1. Initiate robot and ask operators to load the device.
  2. Prepare DUT to start movement.
  3. Move the robot arm according to the given positions.
  4. After finishing movement, kick off the computation.
  5. Push the results.
  6. Log the files and results.
  """

  ARGS = [
      Arg('robot_fixture', str,
          'The class name of the robot fixture under '
          '``cros.factory.test.fixture``, should '
          'be a subclass of ``cros.factory.test.fixture.imu.robot.Robot``.'
          'E.g. robot.dummy_robot.DummyRobot'),
      Arg('robot_fixture_args', dict,
          'A dict of the args used for the constructor of the robot_fixture.',
          default={}),
      Arg('algorithm', str,
          'The class name of the computing method under '
          '``cros.factory.test.fixture``, should be a subclass of '
          '``cros.factory.test.fixture.robot.algorithm.BaseAlgorithm``.'
          'E.g. robot.dummy_algorithm.DummyAlgorithm'),
      Arg('algorithm_args', dict,
          'A dict of the args used for the constructor of the algorithm.',
          default={}),
      Arg('period_between_movement', (float, int),
          'The pause period between two movements.', default=0.5),
      Arg('period_after_movement', (float, int),
          'The pause period after the final movements.', default=0.0),
      Arg('positions', list,
          'A list of position index for the robot to move.'),
      Arg('upload_to_server', bool,
          'If true, upload log to factory server after running.',
          default=False),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._robot = fixture_utils.CreateFixture(
        self.args.robot_fixture, self.args.robot_fixture_args)
    self._algorithm = fixture_utils.CreateFixture(
        self.args.algorithm, self.args.algorithm_args)
    self._algorithm.SetLogger(session.console)

    self.ui.ToggleTemplateClass('font-large', True)

  def tearDown(self):
    try:
      self._robot.SetLED(False)
      self._robot.LoadDevice(False)
      self._robot.SetMotor(False)
    except Exception:
      pass
    self._robot.Disconnect()

  def Initialize(self):
    """Initializes the robot.

    Intializes robot and move it to the LOAD / UNLOAD position.
    """
    self.ui.SetState(_('Initializing Robot...'))
    session.console.info('Intializing robot.')
    self._robot.Connect()
    self._robot.SetMotor(True)

  def LoadDevice(self):
    """Ask operator to load DUT."""
    self.ui.SetState(
        _('Please load DUT onto the robot, connect all cables, '
          'and press <b>SPACE</b> to continue.'))
    self._robot.LoadDevice(False)

    session.console.info('Wait for operators to press SPACE.')
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
    session.console.info('SPACE pressed by operator.')

    self.ui.SetState(_('Prepare for movement.'))
    self._robot.LoadDevice(True)

  def StartMoving(self):
    """Starts movement process."""
    self.ui.SetState(_('Moving to start position...'))

    session.console.info('Start to move.')
    self._robot.SetLED(True)
    self._algorithm.OnStartMoving(self._dut)

    for position in self.args.positions:
      session.console.info('Move to position %d.', position)
      self._robot.MoveTo(position)
      self.Sleep(self.args.period_between_movement)

    self.Sleep(self.args.period_after_movement)

    self._algorithm.OnStopMoving(self._dut)

    self.ui.SetState(_('Moving to LOAD / UNLOAD position...'))
    self._robot.SetLED(False)
    # Shutdown and disconnect robot here to avoid robot overload during
    # computing.
    self._robot.LoadDevice(False)
    self._robot.SetMotor(False)
    self._robot.Disconnect()

  def Compute(self):
    """Starts computing after the movement."""
    self.ui.SetState(_('Computing...'))
    session.console.info('Compute for %s', self._dut.info.serial_number)
    self._algorithm.Compute(self._dut)

  def PushResult(self):
    """Pushes the result to the DUT."""
    self.ui.SetState(_('Pushing the result...'))
    session.console.info('Pushing the result.')

    self._algorithm.PullResult(self._dut)

  def runTest(self):
    serial_number = self._dut.info.serial_number
    if not serial_number:
      self.fail('Failed to get the device SN')

    session.console.info('SN: %s', serial_number)
    logging.info('SN: %s', serial_number)
    self.Initialize()
    self.LoadDevice()
    self.StartMoving()
    self.Compute()
    self.PushResult()
    if self.args.upload_to_server:
      self._algorithm.UploadLog(self._dut, server_proxy.GetServerProxy())
