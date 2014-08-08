#!/usr/bin/python -Bu
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the test_factory_flow tool."""


import os
import shutil
import tempfile
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow import test_factory_flow
from cros.factory.factory_flow.test_factory_flow import TestStatus
from cros.factory.tools import build_board
from cros.factory.utils import file_utils


TEST_CONFIG = os.path.join(os.path.dirname(__file__), 'testdata',
                           'test_config.yaml')


class TestResultUnittest(unittest.TestCase):
  """Unit tests for TestResult class."""
  def setUp(self):
    self.board = 'big'
    self.test_config = test_factory_flow.LoadConfig(filepath=TEST_CONFIG)
    self.base_log_dir = tempfile.mkdtemp(prefix='test_factory_flow.')
    self.bundle_dir = tempfile.mkdtemp(prefix='test_bundle.')

  def tearDown(self):
    shutil.rmtree(self.base_log_dir)
    shutil.rmtree(self.bundle_dir)

  def testTestItemCstor(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)
    # All the test status should be initialized as NOT_TESTED.
    for item_results in test_result.results.itervalues():
      self.assertTrue(
          all(result.status == TestStatus.NOT_TESTED)
          for result in item_results.itervalues())

  def testSetTestItemResult(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)

    # Basic test.
    test_result.SetTestItemResult(
        'big_dut_wifi', 'start_server',
        test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))
    self.assertEquals(
        TestStatus.PASSED,
        test_result.results['big_dut_wifi']['start_server'].status)
    self.assertEquals(
        'log/path',
        test_result.results['big_dut_wifi']['start_server'].log_file)

    # Test invalid dut.
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        r"DUT 'foo_dut' is not planned for 'stress_and_grt'",
        test_result.SetTestItemResult, 'foo_dut', 'start_server',
        test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))

    # Test invalid test plan.
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        r"Test item 'foo_item' is not planned for 'stress_and_grt'",
        test_result.SetTestItemResult, 'big_dut_wifi', 'foo_item',
        test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))

  def testGetOverallTestResult(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)

    # Overall status should be NOT_TESTED if all test items were not tested.
    self.assertEquals(TestStatus.NOT_TESTED, test_result.GetOverallTestResult())

    # Overall status should be PASSED if all test items passed.
    for dut in self.test_config['test_plans'][plan]['dut']:
      for item in self.test_config['test_plans'][plan]['test_sequence']:
        test_result.SetTestItemResult(
            dut, item,
            test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))
      for item in self.test_config['test_plans'][plan]['clean_up']:
        test_result.SetTestItemResult(
            dut, item,
            test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))
    self.assertEquals(TestStatus.PASSED, test_result.GetOverallTestResult())

    # Overall status should be FAILED if any test item failed.
    test_result.SetTestItemResult(
        'big_dut_wifi', 'start_server',
        test_factory_flow.TestResultInfo(TestStatus.FAILED, 'log/path'))
    self.assertEquals(TestStatus.FAILED, test_result.GetOverallTestResult())

  def testGenerateOverallTestReport(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)

    for dut in self.test_config['test_plans'][plan]['dut']:
      for item in self.test_config['test_plans'][plan]['test_sequence']:
        test_result.SetTestItemResult(
            dut, item,
            test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))
      for item in self.test_config['test_plans'][plan]['clean_up']:
        test_result.SetTestItemResult(
            dut, item,
            test_factory_flow.TestResultInfo(TestStatus.PASSED, 'log/path'))
    report = test_result.GenerateReport()

    # Overall test results should be PASSED.
    self.assertEquals(TestStatus.PASSED, report['overall_status'])
    self.assertEquals(
        TestStatus.PASSED, report['duts']['big_dut_wifi']['overall_status'])

    # Test items should be stored in sequence.
    first_test_item = report['duts']['big_dut_wifi']['test_sequence'][0]
    self.assertEquals(
        'create_bundle_toolkit_latest', first_test_item.keys()[0])
    self.assertEquals(
        TestStatus.PASSED, first_test_item.values()[0]['status'])
    self.assertEquals(
        'log/path', first_test_item.values()[0]['log_file'])


class LocateBundleDirUnittest(unittest.TestCase):
  def setUp(self):
    self.base_dir = tempfile.mkdtemp(prefix='bundle_dir.')
    self.board = build_board.BuildBoard('big')

  def tearDown(self):
    shutil.rmtree(self.base_dir)

  def testLocateBundleDir(self):
    # No testing bundle in base_dir. This should raise an exception.
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        (r'Unable to locate the testing bundle directory; expect to find one '
         r'bundle in .*'),
        test_factory_flow.LocateBundleDir, self.board, self.base_dir)

    bundle_dir = os.path.join(
        self.base_dir, 'factory_bundle_nyan_big_20140809_testing')
    file_utils.TryMakeDirs(bundle_dir)

    # The function should locate the testing bundle directory for the following
    # two calls.
    self.assertEquals(
        bundle_dir, test_factory_flow.LocateBundleDir(self.board, bundle_dir))
    self.assertEquals(
        bundle_dir,
        test_factory_flow.LocateBundleDir(self.board, self.base_dir))

    # The function should raise an exception if there are more than one testing
    # bundle found.
    extra_bundle_dir = os.path.join(
        self.base_dir, 'factory_bundle_nyan_big_20140810_testing')
    file_utils.TryMakeDirs(extra_bundle_dir)
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        r'Found 2 bundles in .*; expect to find only one\.',
        test_factory_flow.LocateBundleDir, self.board, self.base_dir)


if __name__ == '__main__':
  unittest.main()
