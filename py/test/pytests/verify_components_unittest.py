#!/usr/bin/env python
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for verify_components factory test."""

import json
import logging
import subprocess
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test.pytests import verify_components
from cros.factory.test import test_ui
from cros.factory.test.utils.deploy_utils import FactoryPythonArchive
from cros.factory.utils import type_utils


class FakeArgs(object):
  def __init__(self, dargs):
    self.__dict__ = dargs


_MOX_HTML_TYPE = mox.Or(mox.IsA(list), mox.IsA(basestring), mox.IsA(dict))


class VerifyComponentsUnitTest(unittest.TestCase):
  """Unit tests for verify_components factory test."""

  def setUp(self):
    self._mox = mox.Mox()

    self._mock_test = verify_components.VerifyComponentsTest()
    self._mock_test.factory_par = self._mox.CreateMock(FactoryPythonArchive)
    self._mock_test.ui = self._mox.CreateMock(test_ui.StandardUI)
    self._mox.StubOutWithMock(event_log, 'Log')
    self.fake_phase = 'EVT'

  def tearDown(self):
    self._mox.UnsetStubs()

  def testCheckComponentsTaskPass(self):
    self._mock_test.args = FakeArgs({
        'component_list': ['camera', 'cpu'],
        'fast_fw_probe': False,
        'enable_factory_server': False,
        'phase': self.fake_phase})
    command = ['hwid', 'verify-components', '--json_output',
               '--no-fast-fw-probe', '--components', 'camera,cpu',
               '--phase', self.fake_phase]
    # good probed results
    probed = {
        u'camera': [{
            u'component_name': u'CAMERA_1',
            u'probed_values': {
                u'hardware': {
                    u'raw_value': u'CAMERA_HAREWARE',
                    u'is_re': False}},
            u'error': None}],
        u'cpu': [{
            u'component_name': u'CPU_1',
            u'probed_values': {
                u'hardware': {
                    u'raw_value': u'CPU_HARDWARE',
                    u'is_re': False}},
            u'error': None}]}

    self._mock_test.ui.SetState(_MOX_HTML_TYPE)
    self._mock_test.factory_par.CheckOutput(command).AndReturn(
        json.dumps(probed))

    event_log.Log('probed_components', results=probed)

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
        'enable_factory_server': False,
        'phase': self.fake_phase})
    command = ['hwid', 'verify-components', '--json_output',
               '--no-fast-fw-probe', '--components', 'camera,cpu',
               '--phase', self.fake_phase]
    # bad probed results
    probed = {
        u'camera': [{
            u'component_name': u'CAMERA_1',
            u'probed_values': {
                u'hardware': {
                    u'raw_value': u'CAMERA_HAREWARE',
                    u'is_re': False}},
            u'error': None}],
        u'cpu': [{
            u'component_name': None,
            u'probed_values': None,
            u'error': u'Fake error'}]}

    self._mock_test.ui.SetState(_MOX_HTML_TYPE)
    self._mock_test.factory_par.CheckOutput(command).AndReturn(
        json.dumps(probed))

    event_log.Log('probed_components', results=probed)

    self._mox.ReplayAll()
    with self.assertRaises(type_utils.TestFailure):
      self._mock_test.runTest()
    self._mox.VerifyAll()

  def testCheckComponentsTaskException(self):
    """Test for call process error."""

    self._mock_test.args = FakeArgs({
        'component_list': ['camera', 'cpu'],
        'fast_fw_probe': False,
        'enable_factory_server': False,
        'phase': self.fake_phase})
    command = ['hwid', 'verify-components', '--json_output',
               '--no-fast-fw-probe', '--components', 'camera,cpu',
               '--phase', self.fake_phase]

    self._mock_test.ui.SetState(_MOX_HTML_TYPE)
    self._mock_test.factory_par.CheckOutput(command).AndRaise(
        subprocess.CalledProcessError(1, 'Fake command'))

    self._mox.ReplayAll()
    with self.assertRaises(subprocess.CalledProcessError):
      self._mock_test.runTest()
    self._mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
