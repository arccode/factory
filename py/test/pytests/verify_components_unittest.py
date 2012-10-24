#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import Gooftool
from cros.factory.gooftool import Mismatch
from cros.factory.gooftool import ProbedComponentResult
from cros.factory.test.pytests import verify_components
from cros.factory.test.pytests.verify_components import CheckComponentsTask
from cros.factory.test.pytests.verify_components import VerifyAnyBOMTask
from cros.factory.test.ui_templates import OneSection

class VerifyComponentsUnitTest(unittest.TestCase):
  def setUp(self):
    self._mox = mox.Mox()

    # mocks for setting up _mock_test used for FactoryTask tests
    self._mock_test = self._mox.CreateMock(
        verify_components.VerifyComponentsTest)
    self._mock_test.gooftool = self._mox.CreateMock(Gooftool)
    self._mock_test.template = self._mox.CreateMock(OneSection)
    self._mock_test.board = "BENDER"

  def tearDown(self):
    self._mox.VerifyAll()
    self._mox.UnsetStubs()

  def _StubPassFail(self, task):
    """Stub out Pass() and Fail() for FactoryTasks since their logic is not
    interested to unit tests here.
    """

    self._mox.StubOutWithMock(task, "Pass")
    self._mox.StubOutWithMock(task, "Fail")


  def testCheckComponentsTaskPass(self):
    task = CheckComponentsTask(self._mock_test)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    # good probed results
    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult('cpu_1', 'CPU_1', None)]}
    self._mock_test.gooftool.VerifyComponents(
        self._mock_test.component_list).AndReturn(probed)

    task.Pass()

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskFailed(self):
    task = CheckComponentsTask(self._mock_test)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    # bad probed results
    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult(None, 'CPU_1', "Fake error")]}
    self._mock_test.gooftool.VerifyComponents(
        self._mock_test.component_list).AndReturn(probed)

    task.Fail(mox.IsA(str))

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskException(self):
    task = CheckComponentsTask(self._mock_test)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    self._mock_test.gooftool.VerifyComponents(
        self._mock_test.component_list).AndRaise(ValueError('Fake Error'))

    task.Fail(mox.IsA(str))

    self._mox.ReplayAll()
    task.Run()

  def testVerifyAnyBOMTaskPass(self):
    task = VerifyAnyBOMTask(self._mock_test, ['LEELA'])
    self._StubPassFail(task)
    self._mock_test.probed_results = (
        {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)]})

    self._mock_test.template.SetState(mox.IsA(unicode))

    self._mock_test.gooftool.FindBOMMismatches(
        'BENDER', 'LEELA', self._mock_test.probed_results).AndReturn({})

    task.Pass()

    self._mox.ReplayAll()
    task.Run()

  def testVerifyAnyBOMTaskFail(self):
    task = VerifyAnyBOMTask(self._mock_test, ['LEELA'])
    self._StubPassFail(task)
    self._mock_test.probed_results = (
        {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
         'cpu':[ProbedComponentResult('cpu_2', 'cpu_2', None)]})

    self._mock_test.template.SetState(mox.IsA(unicode))

    self._mock_test.gooftool.FindBOMMismatches(
        'BENDER', 'LEELA', self._mock_test.probed_results).AndReturn(
            {'cpu': Mismatch(set(['cpu_1']), set(['cpu_2']))})

    task.Fail(mox.IsA(str))

    self._mox.ReplayAll()
    task.Run()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()

