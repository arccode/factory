#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for verify_components factory test."""

import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3.common import ProbedComponentResult
from cros.factory.hwid.v3.database import Database
from cros.factory.test import shopfloor
from cros.factory.test.factory import FactoryTestFailure
from cros.factory.test.pytests import verify_components
from cros.factory.test.ui_templates import OneSection

class FakeArgs(object):
  def __init__(self, dargs):
    self.__dict__ = dargs


class VerifyComponentsUnitTest(unittest.TestCase):
  """Unit tests for verify_components factory test."""

  def setUp(self):
    self._mox = mox.Mox()

    self._mock_test = verify_components.VerifyComponentsTest()
    self._mock_shopfloor = self._mox.CreateMock(shopfloor)
    self._mock_test.template = self._mox.CreateMock(OneSection)
    verify_components.hwid_utils = self._mox.CreateMock(hwid_utils)
    verify_components.database.Database = self._mox.CreateMock(Database)
    self._mox.StubOutWithMock(verify_components, 'Log')

  def tearDown(self):
    self._mox.UnsetStubs()

  def testCheckComponentsTaskPass(self):
    self._mock_test.args = FakeArgs({
        'component_list': ['camera', 'cpu'],
        'fast_fw_probe': False,
        'skip_shopfloor': True})
    # good probed results
    probed = {'camera': [ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult('cpu_1', 'CPU_1', None)]}

    self._mock_test.template.SetState(mox.IsA(unicode))
    verify_components.database.Database.Load().AndReturn('fake database')
    verify_components.hwid_utils.GetProbedResults(
        fast_fw_probe=False).AndReturn('fake probed results')
    verify_components.hwid_utils.VerifyComponents(
        'fake database', 'fake probed results',
        self._mock_test.args.component_list).AndReturn(probed)
    verify_components.Log('probed_components', results=probed)

    self._mox.ReplayAll()
    self._mock_test.runTest()
    self._mox.VerifyAll()
    # esnure the result is appended
    self.assertEquals(probed, self._mock_test.probed_results)

  def testCheckComponentsTaskFailed(self):
    """Test for component name not found error with HWIDv3."""
    self._mock_test.args = FakeArgs({
        'component_list': ['camera', 'cpu'],
        'fast_fw_probe': False,
        'skip_shopfloor': True})
    # bad probed results
    probed = {'camera': [ProbedComponentResult('camera_1', 'CAMERA_1', None)],
              'cpu': [ProbedComponentResult(None, 'CPU_1', 'Fake error')]}

    self._mock_test.template.SetState(mox.IsA(unicode))
    verify_components.database.Database.Load().AndReturn('fake database')
    verify_components.hwid_utils.GetProbedResults(
        fast_fw_probe=False).AndReturn('fake probed results')
    verify_components.hwid_utils.VerifyComponents(
        'fake database', 'fake probed results',
        self._mock_test.args.component_list).AndReturn(probed)
    verify_components.Log('probed_components', results=probed)

    self._mox.ReplayAll()
    with self.assertRaises(FactoryTestFailure):
      self._mock_test.runTest()
    self._mox.VerifyAll()

  def testCheckComponentsTaskException(self):
    self._mock_test.args = FakeArgs({
        'component_list': ['camera', 'cpu'],
        'fast_fw_probe': False,
        'skip_shopfloor': True})

    self._mock_test.template.SetState(mox.IsA(unicode))
    verify_components.database.Database.Load().AndReturn('fake database')
    verify_components.hwid_utils.GetProbedResults(
        fast_fw_probe=False).AndRaise(ValueError('fake probed results'))

    self._mox.ReplayAll()
    with self.assertRaises(ValueError):
      self._mock_test.runTest()
    self._mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
