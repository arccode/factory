#!/usr/bin/python -Bu
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the test_factory_flow tool."""

from __future__ import print_function

import os
import shutil
import tempfile
import unittest
import yaml

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
    self.board = 'rambi'
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

  def testGetTestItemResult(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)

    # Basic test.
    item_result = test_result.GetTestItemResult(
        'rambi_dut_wifi', 'start_server')
    self.assertEquals(TestStatus.NOT_TESTED, item_result.status)

    # Test invalid dut.
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        r"DUT 'foo_dut' is not planned for 'stress_and_grt'",
        test_result.GetTestItemResult, 'foo_dut', 'start_server')

    # Test invalid test plan.
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        r"Test item 'foo_item' is not planned for 'stress_and_grt'",
        test_result.GetTestItemResult, 'rambi_dut_wifi', 'foo_item')

  def testGetOverallTestResult(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)

    # Overall status should be NOT_TESTED if all test items were not tested.
    self.assertEquals(TestStatus.NOT_TESTED, test_result.GetOverallTestResult())

    # Overall status should be PASSED if all test items passed.
    for dut in self.test_config['test_plans'][plan]['dut']:
      for x in ('test_sequence', 'clean_up'):
        for item in self.test_config['test_plans'][plan][x]:
          item_result = test_result.GetTestItemResult(dut, item)
          item_result.status = TestStatus.PASSED
          item_result.log_file = 'log/path'
    self.assertEquals(TestStatus.PASSED, test_result.GetOverallTestResult())

    # Overall status should be FAILED if any test item failed.
    item_result = test_result.GetTestItemResult(
        'rambi_dut_wifi', 'start_server')
    item_result.status = TestStatus.FAILED
    self.assertEquals(TestStatus.FAILED, test_result.GetOverallTestResult())

  def testGenerateOverallTestReport(self):
    plan = 'stress_and_grt'
    test_result = test_factory_flow.TestResult(
        self.board, plan, self.test_config['test_plans'][plan],
        self.base_log_dir, self.bundle_dir)

    for dut in self.test_config['test_plans'][plan]['dut']:
      for x in ('test_sequence', 'clean_up'):
        for item in self.test_config['test_plans'][plan][x]:
          item_result = test_result.GetTestItemResult(dut, item)
          item_result.status = TestStatus.PASSED
          item_result.log_file = 'log/path'
    report = test_result.GenerateReport()

    # Overall test results should be PASSED.
    self.assertEquals(TestStatus.PASSED, report['overall_status'])
    self.assertEquals(
        TestStatus.PASSED, report['duts']['rambi_dut_wifi']['overall_status'])

    # Test items should be stored in sequence.
    first_test_item = report['duts']['rambi_dut_wifi']['test_sequence'][0]
    self.assertEquals(
        'create_bundle_toolkit_latest', first_test_item.keys()[0])
    self.assertEquals(
        TestStatus.PASSED, first_test_item.values()[0]['status'])
    self.assertEquals(
        'log/path', first_test_item.values()[0]['log_file'])


class FactoryFlowRunnerUnittest(unittest.TestCase):

  def setUp(self):
    self.board = 'rambi'
    self.test_config = test_factory_flow.LoadConfig(filepath=TEST_CONFIG)
    self.base_log_dir = tempfile.mkdtemp(prefix='test_factory_flow.')
    self.bundle_dir = tempfile.mkdtemp(prefix='test_bundle.')
    self.runner = test_factory_flow.FactoryFlowRunner(
        self.test_config, log_dir=self.base_log_dir, bundle_dir=self.bundle_dir)
    # Patch the following two functions to make them no-op since we don't need
    # them in the unit tests.
    self.runner.GetDUTFactoryLogs = lambda plan, dut, output_patn: None
    self.original_NotifyOwners = test_factory_flow.TestResult.NotifyOwners
    test_factory_flow.TestResult.NotifyOwners = (
        test_factory_flow.TestResult.GenerateLogArchive)

  def tearDown(self):
    self.runner.CleanUp()
    shutil.rmtree(self.base_log_dir)
    shutil.rmtree(self.bundle_dir)
    test_factory_flow.TestResult.NotifyOwners = self.original_NotifyOwners

  def testRunTestsPassing(self):
    # This should pass without raising any exception.
    self.runner.RunTests(plan='passing_test_plan')
    with open(os.path.join(self.base_log_dir, 'passing_test_plan',
                           test_factory_flow.TEST_RUN_REPORT_FILE)) as f:
      report = yaml.load(f.read())
    # Verify that all report fields are correct. The report should look like:
    #
    #  test_plan: passing_test_plan
    #  board: rambi
    #  overall_status: PASSED
    #  start_time: 1408287612.780922
    #  end_time: 1408287613.471451
    #  duts:
    #    rambi_dut_wifi:
    #      overall_status: PASSED
    #      test_sequence:
    #      - passing_item:
    #          end_time: 1408287613.126839
    #          log_file: \
    #  /tmp/test_factory_flow.vNvgvq/passing_test_plan/passing_item.0.log
    #          start_time: 1408287612.784149
    #          status: PASSED
    #      clean_up:
    #      - clean_up_item:
    #          end_time: 1408287613.471366
    #          log_file: \
    #  /tmp/test_factory_flow.vNvgvq/passing_test_plan/clean_up_item.0.log
    #          start_time: 1408287613.130337
    #          status: PASSED
    self.assertIn('rambi_dut_wifi', report['duts'])
    self.assertEquals('passing_test_plan', report['test_plan'])
    self.assertEquals(TestStatus.PASSED, report['overall_status'])
    self.assertLess(report['start_time'], report['end_time'])
    dut_result = report['duts']['rambi_dut_wifi']
    self.assertEquals(TestStatus.PASSED, dut_result['overall_status'])
    self.assertIn('passing_item', dut_result['test_sequence'][0])
    passing_item = dut_result['test_sequence'][0].values()[0]
    self.assertEqual(TestStatus.PASSED, passing_item['status'])
    self.assertLess(passing_item['start_time'], passing_item['end_time'])
    self.assertIn('clean_up_item', dut_result['clean_up'][0])
    clean_up_item = dut_result['clean_up'][0].values()[0]
    self.assertEqual(TestStatus.PASSED, clean_up_item['status'])
    self.assertLess(clean_up_item['start_time'], clean_up_item['end_time'])

  def testRunTestsFailing(self):
    # This should fail without raising any exception.
    self.runner.RunTests(plan='failing_test_plan')

    with open(os.path.join(self.base_log_dir, 'failing_test_plan',
                           test_factory_flow.TEST_RUN_REPORT_FILE)) as f:
      report = yaml.load(f.read())
    # Verify that all report fields are correct. The report should look like:
    #
    #  test_plan: passing_test_plan
    #  board: rambi
    #  overall_status: FAILED
    #  start_time: 1408287612.780922
    #  end_time: 1408287613.471451
    #  duts:
    #    rambi_dut_wifi:
    #      overall_status: FAILED
    #      test_sequence:
    #      - failing_item:
    #          end_time: 1408287613.126839
    #          log_file: \
    #  /tmp/test_factory_flow.vNvgvq/passing_test_plan/failing_item.0.log
    #          start_time: 1408287612.784149
    #          status: FAILED
    #      clean_up:
    #      - clean_up_item:
    #          end_time: 1408287613.471366
    #          log_file: \
    #  /tmp/test_factory_flow.vNvgvq/passing_test_plan/clean_up_item.0.log
    #          start_time: 1408287613.130337
    #          status: PASSED
    self.assertIn('rambi_dut_wifi', report['duts'])
    self.assertEquals('failing_test_plan', report['test_plan'])
    self.assertEquals(TestStatus.FAILED, report['overall_status'])
    self.assertLess(report['start_time'], report['end_time'])
    dut_result = report['duts']['rambi_dut_wifi']
    self.assertEquals(TestStatus.FAILED, dut_result['overall_status'])
    self.assertIn('failing_item', dut_result['test_sequence'][0])
    failing_item = dut_result['test_sequence'][0].values()[0]
    self.assertEqual(TestStatus.FAILED, failing_item['status'])
    self.assertLess(failing_item['start_time'], failing_item['end_time'])
    self.assertIn('clean_up_item', dut_result['clean_up'][0])
    clean_up_item = dut_result['clean_up'][0].values()[0]
    self.assertEqual(TestStatus.PASSED, clean_up_item['status'])
    self.assertLess(clean_up_item['start_time'], clean_up_item['end_time'])


class LocateBundleDirUnittest(unittest.TestCase):

  def setUp(self):
    self.base_dir = tempfile.mkdtemp(prefix='bundle_dir.')
    self.board = build_board.BuildBoard('rambi')

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
        self.base_dir, 'factory_bundle_rambi_20140809_testing')
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
        self.base_dir, 'factory_bundle_rambi_20140810_testing')
    file_utils.TryMakeDirs(extra_bundle_dir)
    self.assertRaisesRegexp(
        test_factory_flow.FactoryFlowTestError,
        r'Found 2 bundles in .*; expect to find only one\.',
        test_factory_flow.LocateBundleDir, self.board, self.base_dir)


if __name__ == '__main__':
  unittest.main()
