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
from cros.factory.hwid.common import ProbedComponentResult
from cros.factory.test import shopfloor
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
    setattr(self._mock_test, 'args',
            type('mock_version', (), {'hwid_version': 2,
                                      'fast_fw_probe': False}))
    self._mock_test.args.hwid_version = 2
    self._mock_test.gooftool = self._mox.CreateMock(Gooftool)
    self._mock_shopfloor = self._mox.CreateMock(shopfloor)
    self._mock_test.template = self._mox.CreateMock(OneSection)
    self._mock_test.board = "BENDER"

    self._mox.StubOutWithMock(verify_components, 'Log')

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
    verify_components.Log("probed_components", result=probed)

    task.Pass()

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskPassV3(self):
    self._mock_test.args.hwid_version = 3
    task = CheckComponentsTask(self._mock_test)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    # good probed results
    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult('cpu_1', 'CPU_1', None)]}
    self._mock_test.gooftool.VerifyComponentsV3(
        self._mock_test.component_list, fast_fw_probe=False).AndReturn(probed)
    verify_components.Log("probed_components", result=probed)

    task.Pass()

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended

  def testCheckComponentsTaskFailed(self):
    '''Test for component name not found error.'''

    task = CheckComponentsTask(self._mock_test)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    # bad probed results
    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult(None, 'CPU_1', "Fake error")]}
    self._mock_test.gooftool.VerifyComponents(
        self._mock_test.component_list).AndReturn(probed)
    verify_components.Log("probed_components", result=probed)

    task.Fail(mox.IsA(str))

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskFailedV3(self):
    '''Test for component name not found error with HWIDv3.'''

    self._mock_test.args.hwid_version = 3
    task = CheckComponentsTask(self._mock_test)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    # bad probed results
    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult(None, 'CPU_1', "Fake error")]}
    self._mock_test.gooftool.VerifyComponentsV3(
        self._mock_test.component_list, fast_fw_probe=False).AndReturn(probed)
    verify_components.Log("probed_components", result=probed)

    task.Fail(mox.IsA(str))

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskAllowMissing(self):
    '''Test for component missing error when it is allowed.'''

    task = CheckComponentsTask(self._mock_test, allow_missing=True)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              # Missing is allowed.
              'cpu': [ProbedComponentResult(None, None, "Fake missing error")]}
    self._mock_test.gooftool.VerifyComponents(
        self._mock_test.component_list).AndReturn(probed)
    verify_components.Log("probed_components", result=probed)

    task.Pass()

    self._mox.ReplayAll()
    task.Run()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskNotAllowMissing(self):
    '''Test for component missing error when it is NOT allowed.'''

    task = CheckComponentsTask(self._mock_test, allow_missing=False)
    self._StubPassFail(task)
    self._mock_test.component_list = ['camera', 'cpu']

    self._mock_test.template.SetState(mox.IsA(unicode))

    probed = {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              # Missing is not allowed and should be captured.
              'cpu': [ProbedComponentResult(None, None, "Fake missing error")]}
    self._mock_test.gooftool.VerifyComponents(
        self._mock_test.component_list).AndReturn(probed)
    verify_components.Log("probed_components", result=probed)

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
    verify_components.Log("bom_whitelist", whitelist=['LEELA'])
    self._StubPassFail(task)
    self._mock_test.probed_results = (
        {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)]})

    self._mock_test.template.SetState(mox.IsA(unicode))

    self._mock_test.gooftool.FindBOMMismatches(
        'BENDER', 'LEELA', self._mock_test.probed_results).AndReturn({})
    verify_components.Log("verified_bom", bom='LEELA')

    task.Pass()

    self._mox.ReplayAll()
    task.Run()

  def testVerifyAnyBOMTaskFail(self):
    task = VerifyAnyBOMTask(self._mock_test, ['LEELA'])
    self._StubPassFail(task)
    verify_components.Log("bom_whitelist", whitelist=['LEELA'])
    self._mock_test.probed_results = (
        {'camera':[ProbedComponentResult('camera_1', 'CAMERA_1', None)],
         'cpu':[ProbedComponentResult('cpu_2', 'cpu_2', None)]})

    self._mock_test.template.SetState(mox.IsA(unicode))

    mismatched = {'cpu': Mismatch(set(['cpu_1']), set(['cpu_2']))}
    self._mock_test.gooftool.FindBOMMismatches(
        'BENDER', 'LEELA', self._mock_test.probed_results).AndReturn(
            mismatched)
    verify_components.Log("failed_matching_bom",
        all_mismatches={'LEELA': mismatched})

    task.Fail(mox.IsA(str))

    self._mox.ReplayAll()
    task.Run()

  def testLookupBOMList(self):
    stub_table = "table"
    self._mock_shopfloor.get_server_url().MultipleTimes().AndReturn(
        "http://StubUrl.com")
    self._mock_shopfloor.get_selected_aux_data(
        stub_table).MultipleTimes().AndReturn(
           {"field_1": 1, "field_2": 2, "field_3": 3})

    self._mox.ReplayAll()
    stub_mapping = {1: ["BLUE"], 2: ["RED"]}

    # tests to cover both mapping cases
    self.assertEquals(
      ["BLUE"],
      verify_components.LookupBOMList(self._mock_shopfloor, stub_table,
                                      "field_1", stub_mapping))
    self.assertEquals(
      ["RED"],
      verify_components.LookupBOMList(self._mock_shopfloor, stub_table,
                                      "field_2", stub_mapping))

    # the field and its value exist but no BOM mapping
    self.assertRaises(
      ValueError,
      verify_components.LookupBOMList, self._mock_shopfloor, stub_table,
                                       "field_3", stub_mapping)
    # the field doesn't exist
    self.assertRaises(
      ValueError,
      verify_components.LookupBOMList, self._mock_shopfloor, stub_table,
                                       "field_4", stub_mapping)

  def testLookupBOMListNoShopfloor(self):
    self._mock_shopfloor.get_server_url().AndReturn("")

    self._mox.ReplayAll()

    self.assertRaises(
      ValueError,
      verify_components.LookupBOMList,
      self._mock_shopfloor, "table", "field_1", [])

  def testLookupBOMListNoAuxTable(self):
    self._mock_shopfloor.get_server_url().AndReturn("http://StubUrl.com")
    self._mock_shopfloor.get_selected_aux_data("table").AndRaise(ValueError)

    self._mox.ReplayAll()

    self.assertRaises(
      ValueError,
      verify_components.LookupBOMList,
      self._mock_shopfloor, "table", "field_1", [])


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()

