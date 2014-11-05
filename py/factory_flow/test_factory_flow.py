#!/usr/bin/python -Bu
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A tool for running factory flow tests."""

from __future__ import print_function

import collections
import glob
import logging
import os
import re
import shutil
import smtplib
import subprocess
import tempfile
import time
import yaml
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import factory_common   # pylint: disable=W0611
from cros.factory.common import MakeList
from cros.factory.factory_flow import common
from cros.factory.factory_flow import test_runner_common
from cros.factory.hacked_argparse import CmdArg, ParseCmdline, verbosity_cmd_arg
from cros.factory.test import utils
from cros.factory.tools import build_board
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import ssh_utils
from cros.factory.utils import time_utils


# Set default verbosity to INFO.
verbosity_cmd_arg[1]['default'] = logging.INFO

CONFIG_FILE_PATH_IN_CHROOT = lambda board: os.path.join(
    os.environ['CROS_WORKON_SRCROOT'], 'src', 'platform',
    'factory-private', 'board_testing_config',
    'board_config-%s.yaml' % board)
CONFIG_FILE_PATH_OUTSIDE_CHROOT = lambda board: (
    '/var/factory/board_config-%s.yaml' % board)

TestStatus = utils.Enum(['NOT_TESTED', 'PASSED', 'FAILED'])

TEST_RUN_REPORT_FILE = 'REPORT'
TEST_RUN_RUNNING_FILE = '.running'


class FactoryFlowTestError(Exception):
  """Factory flow runner error."""
  pass


class TestResultInfo(object):
  """A class to hold test result information.

  Properties:
    staus: The status of the test.
    log_file: The path to the test log file.
    start_time: The time the test starts.
    end_time: The time the test ends.
  """
  def __init__(self, status, log_file=None, start_time=None, end_time=None):
    self.status = status
    self.log_file = log_file
    self.start_time = start_time
    self.end_time = end_time


class TestResult(object):
  """A class to hold test results of a test plan.

  Properties:
    board_name: The board name of the test plan.
    test_plan_name: The name of the test plan.
    test_plan_config: The configs of the test plan, as a dict.
    base_log_dir: The path to base log directory.
    bundle_dir: The path to the testing bundle directory.
    start_time: The time that the test starts.
    end_time: The time that the test ends.
    results: The test results of each test item, stored in a per DUT basis.
  """
  def __init__(self, board_name, plan_name, plan_config, base_log_dir,
               bundle_dir):
    self.board_name = build_board.BuildBoard(board_name)
    self.test_plan_name = plan_name
    self.test_plan_config = plan_config
    self.base_log_dir = base_log_dir
    self.test_plan_log_dir = os.path.join(self.base_log_dir,
                                          self.test_plan_name)
    self.bundle_dir = bundle_dir
    self.start_time = None
    self.end_time = None
    self.results = {}
    file_utils.TryMakeDirs(self.test_plan_log_dir)
    # Initialize all items to NOT_TESTED.
    for dut in self.test_plan_config['dut']:
      self.results[dut] = collections.OrderedDict()
      for item in self.test_plan_config['test_sequence']:
        self.results[dut][item] = TestResultInfo(TestStatus.NOT_TESTED)
      for item in self.test_plan_config['clean_up']:
        self.results[dut][item] = TestResultInfo(TestStatus.NOT_TESTED)

  def SetTestPlanRunning(self, is_running):
    """Sets or removes the test running tag file according to is_running."""
    running_tag_file = os.path.join(self.test_plan_log_dir,
                                    TEST_RUN_RUNNING_FILE)
    if is_running:
      self.start_time = time.time()
      file_utils.TouchFile(running_tag_file)
    else:
      self.end_time = time.time()
      os.remove(running_tag_file)

  def GetTestItemResult(self, dut, item):
    """Gets the TestResultInfo object of a test item for the given DUT.

    Args:
      dut: The ID of the DUT.
      item: The ID of the test item.

    Returns:
      The TestResultInfo object storing the test result information.
    """
    if not dut in self.test_plan_config['dut']:
      raise FactoryFlowTestError('DUT %r is not planned for %r' %
                                 (dut, self.test_plan_name))
    if not item in (self.test_plan_config['test_sequence'] +
                    self.test_plan_config['clean_up']):
      raise FactoryFlowTestError('Test item %r is not planned for %r' %
                                 (item, self.test_plan_name))
    return self.results[dut][item]

  def GetOverallTestResult(self, dut=None):
    """Gets the overall test results of the test plan.

    If a DUT is given, return only the overall test result of the DUT.

    Args:
      dut: If given, gets the overall test results of the DUT.

    Returns:
      The overall test results.  This can be:
        - If a DUT is given, the result can be PASSED, FAILED, or NOT_TESTED:
          * PASSED: If all test items of the DUT have passed.
          * NOT_TESTED: If all the test items are not tested.
          * FAILED: None of the above conditions are met.
        - If no DUT is given, the result can be PASSED or FAILED:
          * FAILED: If any of the DUTs planned for this test plan have failed.
          * PASSED: If all the tested DUTs have passed all test items.
    """
    dut_status = {}
    for dut, item_results in self.results.iteritems():
      if all(result.status == TestStatus.PASSED
             for result in item_results.itervalues()):
        dut_status[dut] = TestStatus.PASSED
      elif all(result.status == TestStatus.NOT_TESTED
               for result in item_results.itervalues()):
        dut_status[dut] = TestStatus.NOT_TESTED
      elif any(result.status == TestStatus.FAILED
               for result in item_results.itervalues()):
        dut_status[dut] = TestStatus.FAILED
      else:
        raise FactoryFlowTestError('Unexpected test status')
    if dut:
      return dut_status[dut]
    else:
      return (
          TestStatus.FAILED if any(
              s == TestStatus.FAILED for s in dut_status.itervalues())
          else TestStatus.PASSED)

  def GenerateReport(self):
    """Generates test report as a dictionary.

    Returns:
      A dict of test results.
    """
    # Generate overall test result of the test plan.
    report = {}
    report['board'] = self.board_name.full_name
    report['test_plan'] = self.test_plan_name
    report['overall_status'] = self.GetOverallTestResult()
    report['start_time'] = self.start_time
    report['end_time'] = self.end_time

    # Generate overall test results and specific test result of each test item
    # for each DUT.
    report['duts'] = {}
    for dut, result in self.results.iteritems():
      report['duts'][dut] = {}
      report['duts'][dut]['overall_status'] = self.GetOverallTestResult(dut)

      for section in ('test_sequence', 'clean_up'):
        report['duts'][dut][section] = []
        for item in self.test_plan_config[section]:
          report['duts'][dut][section].append(
              {item: {'status': result[item].status,
                      'log_file': result[item].log_file,
                      'start_time': result[item].start_time,
                      'end_time': result[item].end_time,}
              })

    return report

  def GenerateLogArchive(self):
    """Generates log archive.

    Returns:
      The full path to the generated log archive.
    """
    log_dir = os.path.join(self.base_log_dir, self.test_plan_name)
    if not os.path.exists(log_dir):
      raise FactoryFlowTestError('Log directory of %r not found' %
                                   self.test_plan_name)

    now = time_utils.TimeString(time_separator='-', milliseconds=False)
    log_file_name = '%s-%s-%s.tar.bz2' % (
        self.board_name.full_name, self.test_plan_name, now)
    with open(
        os.path.join(self.base_log_dir, self.test_plan_name,
                     TEST_RUN_REPORT_FILE),
        'w') as f:
      f.write(yaml.dump(self.GenerateReport(), default_flow_style=False))
    process_utils.Spawn(['tar', 'cJvf', log_file_name, self.test_plan_name],
                        cwd=self.base_log_dir, log=True, check_call=True,
                        stdout=process_utils.OpenDevNull())
    return os.path.join(self.base_log_dir, log_file_name)

  def NotifyOwners(self):
    """Sends out notification E-mail to owners of this test plan.

    The notification E-mail contains:
      - Bundle information from the generated README file in the testing bundle.
      - The overall test result of the test plan (PASSED or FAILED).
      - The overall test result of each DUT (PASSED, FAILED, or NOT_TESTED).
      - The test result of each test item on each DUT (PASSED, FAILED, or
        NOT_TESTED).
      - The archived test logs as a attachment.
    """
    log_dir = os.path.join(self.base_log_dir, self.test_plan_name)
    if not os.path.exists(log_dir):
      raise FactoryFlowTestError('Log directory of %r not found' %
                                   self.test_plan_name)

    logging.info('Preparing notification E-mail...')
    report_txt = []

    # Extract the bundle info from README in the testing bundle.
    bundle_dir = LocateBundleDir(self.board_name, self.bundle_dir)
    readme = os.path.join(bundle_dir, 'README')
    if not os.path.exists(readme):
      raise FactoryFlowTestError('Unable to find README in %r' % bundle_dir)
    with open(readme) as f:
      report_txt += [line.strip() for line in f.readlines()]

    # Generate overall test result of the test plan.
    report = self.GenerateReport()
    report_txt += [
        '', '',
        '*** Overall test results: %-20s' % report['overall_status'],
        '***',
        '*** Test result per DUT:',
        '***']

    # Generate overall test results and specific test result of each test item
    # for each DUT.
    for dut in report['duts']:
      report_txt += ['*** [%10s] %s' %
                     (report['duts'][dut]['overall_status'], dut)]
      for section in ('test_sequence', 'clean_up'):
        for item in report['duts'][dut][section]:
          item_name = item.keys()[0]
          item_status = item.values()[0]['status']
          report_txt += ['*** [%10s] - %s' % (item_status, item_name)]
      report_txt += ['***']
    dut_results = MIMEText('\n'.join(report_txt))

    # Generate log archive as a attachment to the E-mail.
    log_archive_path = self.GenerateLogArchive()
    attachment = MIMEBase('application', 'octet-stream')
    with open(log_archive_path, 'rb') as f:
      attachment.set_payload(f.read())
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment',
                          filename=os.path.basename(log_archive_path))

    # Generate the notification E-mail.
    FROM = 'chromeos-factory-testing@chromium.org'
    now = time_utils.TimeString(time_separator='-', milliseconds=False)
    mail = MIMEMultipart()
    mail['Subject'] = ('[%s][%s][%s][%s] Test results and logs.' %
                       (report['overall_status'], self.board_name.full_name,
                        self.test_plan_name, now))
    mail['To'] = ', '.join(self.test_plan_config['owners'])
    mail['From'] = FROM
    mail.attach(dut_results)
    mail.attach(attachment)

    logging.info('Sending notification E-mail to owners...')
    smtp = smtplib.SMTP(net_utils.LOCALHOST)
    smtp.sendmail(FROM, self.test_plan_config['owners'], mail.as_string())
    smtp.quit()


class FactoryFlowRunner(object):
  """A class for running factory flow tests."""

  def __init__(self, config, output_dir=None, log_dir=None, bundle_dir=None):
    self.config = config
    for name, item in config['test_items'].iteritems():
      subcommand = item['command']
      if subcommand not in test_runner_common.CommandBuilder.iterkeys():
        raise FactoryFlowTestError(
            'Invalid subcommand %r in test item %s' % (subcommand, name))
    self.board = config['board']
    self.output_dir = output_dir or tempfile.mkdtemp(
        prefix='factory_flow_runner.')
    self.bundle_dir = bundle_dir or self.output_dir
    # Initialize log directory.
    self.log_dir = log_dir or os.path.join(self.output_dir, 'logs')
    file_utils.TryMakeDirs(self.log_dir)

  def CleanUp(self):
    shutil.rmtree(self.output_dir)

  def RunTests(self, plan=None, dut=None, fail_fast=False):
    """Runs the given test plan.

    Args:
      plan: The test plan to fun.  None to run all test plans.
      dut: The DUT to run factory flow tests on; this should be specified by the
        DUT ID in the config file.  None to test all DUT.
      fail_fast: Whether to fail the test run as soon as a test item fails.
    """
    runner_info = test_runner_common.RunnerInfo({
        'board': self.board,
        'output_dir': self.output_dir,
        })

    host_info = test_runner_common.HostInfo(self.config['host_info'])

    if not plan:
      test_plans_to_run = self.config['test_plans'].keys()
    else:
      if not self.config['test_plans'].get(plan):
        raise FactoryFlowTestError('Unknow test plan %r' % plan)
      test_plans_to_run = MakeList(plan)

    if dut and dut not in self.config['dut_info']:
      raise FactoryFlowTestError('Unknown DUT %r' % dut)

    for plan in test_plans_to_run:
      logging.info('Running test plan %r...', plan)
      config = self.config['test_plans'].get(plan)

      if dut is not None:
        if dut not in config['dut']:
          logging.info('DUT %r is not planned for %r', dut, plan)
          continue
        dut_to_test = MakeList(dut)
      else:
        dut_to_test = config['dut']

      dut_info_dict = {}
      for dut in dut_to_test:
        log_dir = os.path.join(self.log_dir, plan, dut)
        file_utils.TryMakeDirs(log_dir)
        dut_info = test_runner_common.DUTInfo(self.config['dut_info'][dut])
        dut_info['dut_id'] = dut
        dut_info['log_dir'] = log_dir
        dut_info_dict[dut] = dut_info

      test_env = os.environ.copy()
      test_env[common.BUNDLE_DIR_ENVVAR] = self.bundle_dir

      test_result = TestResult(self.board, plan, config, self.log_dir,
                               self.bundle_dir)
      test_result.SetTestPlanRunning(True)

      def RunTestItem(item):
        """Runs a give test item.

        Args:
          item: The test item to run.

        Returns:
          True if the test item passes; False otherwise.
        """
        # Build per-DUT commands.
        test_item = self.config['test_items'][item]
        dut_commands = test_runner_common.CommandBuilder[
            test_item['command']].BuildCommand(
                test_item, runner_info, host_info, dut_info_dict.values())

        # Run all commands concurrently.
        log_file_spec = os.path.join(self.log_dir, plan, item + '.%d.log')
        procs = []
        for x in xrange(len(dut_commands)):
          dut_command = dut_commands[x]
          log_file = log_file_spec % x
          logging.info('Running test item %s for DUT %s...', item,
                       dut_command.duts)
          with open(log_file, 'w') as f:
            proc = process_utils.Spawn(
                dut_command.args, log=True, env=test_env, stdout=f, stderr=f)
          procs.append(
              (dut_command.duts, proc, os.path.relpath(log_file, self.log_dir)))
          for dut in dut_command.duts:
            item_result_info = test_result.GetTestItemResult(dut, item)
            item_result_info.start_time = time.time()
            item_result_info.log_file = log_file

        # Wait for all commands to finish and set test results.
        passed = True
        for x in xrange(len(procs)):
          duts, proc, log_file = procs[x]
          proc.wait()
          for dut in duts:
            item_result_info = test_result.GetTestItemResult(dut, item)

            item_result_info.end_time = time.time()
            if proc.returncode != 0:
              item_result_info.status = TestStatus.FAILED
              logging.error(
                  'Test item %s for DUT %s failed; check %s for detailed logs',
                  item, duts, log_file)
              passed = False
            else:
              item_result_info.status = TestStatus.PASSED
              logging.info(
                  'Test item %s for DUT %s passed; check %s for detailed logs',
                  item, duts, log_file)
        return passed

      try:
        # Run through each test item; abort when any test item fails if
        # fail_fast is True.
        test_item_failed = False
        for item in config['test_sequence']:
          if fail_fast and test_item_failed:
            logging.info(
                'Skip test item %r due to failures of previous test items',
                item)
            continue
          logging.info('Running test item %r...', item)
          if not RunTestItem(item):
            test_item_failed = True
      except Exception:
        logging.exception('Error when running test item %s', item)
        test_item_failed = True
      finally:
        try:
          for dut in dut_to_test:
            self.GetDUTFactoryLogs(plan, dut, log_dir)
        except subprocess.CalledProcessError:
          logging.exception('Unable to get factory logs from DUT')

        # Run through each clean-up item; continue even if one fails.
        for item in config['clean_up']:
          logging.info('Running clean-up item %r...', item)
          try:
            RunTestItem(item)
          except Exception:
            logging.exception('Error when running clean-up item %s', item)

      test_result.SetTestPlanRunning(False)
      test_result.NotifyOwners()

  def GetDUTFactoryLogs(self, plan, dut, output_path):
    """Gets factory logs of the DUT.

    Args:
      plan: The ID of the test plan; used to name the log archive.
      dut: The ID of the DUT to get factory logs from.
      output_path: The output path of the log archive.
    """
    bundle_dir = LocateBundleDir(build_board.BuildBoard(self.board),
                                 self.bundle_dir)
    finalize_report_spec = glob.glob(
        os.path.join(bundle_dir, 'shopfloor', 'shopfloor_data',
                     'reports', time.strftime('logs.%Y%m%d'), '*.tar.xz'))
    if finalize_report_spec:
      # If we find a finalize report, then we assume the DUT has been finalized.
      # Use the finalize report as factory logs of DUT, and do not try to run
      # factory_bug on DUT as SSH is not available in release image.
      if len(finalize_report_spec) > 1:
        logging.warn('Expect to find at most one finalize report but found %d',
                     len(finalize_report_spec))
      for report in finalize_report_spec:
        logging.info('Found finalize report %s', report)
        shutil.move(report, output_path)
      return

    FACTORY_BUG = '/usr/local/factory/bin/factory_bug'
    FACTORY_BUG_ID = '%s-%s' % (plan, dut)

    dut_info = self.config['dut_info'].get(dut)
    if not dut_info:
      raise FactoryFlowTestError('Unknown DUT %r' % dut)
    # Execute factory_bug on the DUT to pack logs.
    ssh_utils.SpawnSSHToDUT(
        [dut_info['ip'], FACTORY_BUG, '--output_dir', '/tmp', '--id',
         FACTORY_BUG_ID], log=True, check_call=True)
    ssh_utils.SpawnRsyncToDUT(
        ['%s:/tmp/factory_bug.%s*.tar.bz2' % (dut_info['ip'], FACTORY_BUG_ID),
         output_path], log=True, check_call=True)


def LocateBundleDir(board, base_path):
  """Locates the testing bundle directory from base_path.

  If the base_path is the testing bundle directory, then returns it. Otherwise
  tries to find exactly one testing bundle directory under base_path.

  Args:
    board: A BuildBoard object.
    base_path: The base path to look for testing bundle directory.

  Returns:
    The full path to the testing bundle directory.
  """
  bundle_dir = base_path
  if not re.match(r'factory_bundle_%s_.*' % board.full_name,
                  os.path.basename(base_path)):
    bundle_dir = glob.glob(os.path.join(
        base_path, 'factory_bundle_%s_*' % board.full_name))
    if not bundle_dir:
      raise FactoryFlowTestError(
          ('Unable to locate the testing bundle directory; expect to find '
           'one bundle in %r') % base_path)
    if len(bundle_dir) > 1:
      raise FactoryFlowTestError(
          'Found %d bundles in %r; expect to find only one.' %
          (len(bundle_dir), base_path))
    bundle_dir = bundle_dir[0]
  return bundle_dir


def LoadConfig(board=None, filepath=None):
  """Loads factory flow testing configurations.

  Args:
    board: The board name of the config file to load.  Used to automatically
      locate config files in pre-defined filepaths.
    filepath: If given, load config file from the given path instead.

  Returns:
    A dict of the loaded config; None if there is no config file for the given
    board.
  """
  if not (board or filepath):
    raise FactoryFlowTestError('Must specify either board or filepath')

  if not filepath:
    board = build_board.BuildBoard(board)
    if utils.in_chroot():
      filepath = CONFIG_FILE_PATH_IN_CHROOT(board.short_name)
    else:
      filepath = CONFIG_FILE_PATH_OUTSIDE_CHROOT(board.short_name)

  if os.path.exists(filepath):
    logging.info('Loading board testing config from %s', filepath)
    with open(filepath) as f:
      return yaml.safe_load(f.read())
  else:
    logging.info('No board testing config file found')
    return None


def main():
  arguments = [
      CmdArg('-b', '--board', help='the board name'),
      CmdArg('-f', '--file', help='the config file'),
      CmdArg('--dut', metavar='DUT_ID',
             help=('the DUT to run factory flow on, '
                   'specified by the DUT ID in the config file')),
      CmdArg('--plan', metavar='TEST_PLAN', help='the test plan to run'),
      CmdArg('--output-dir',
             help='output dir of the created bundle and test logs'),
      CmdArg('--bundle-dir',
             help='path to the base directory of the factory bundle to test'),
      CmdArg('--log-dir',
             help=('path to the base directory to store test logs; '
                   'defaults to "<OUTPUT_DIR>/logs"')),
      CmdArg('--clean-up', action='store_true',
             help='delete generated files and directories after test'),
      CmdArg('--fail-fast', action='store_true',
             help='stop all test items immediately if any error occurrs'),
      verbosity_cmd_arg
  ]
  args = ParseCmdline('Factory flow runner', *arguments)
  logging.basicConfig(
      format=('[%(levelname)s] test_factory_flow ' +
              '%(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=args.verbosity, datefmt='%Y-%m-%d %H:%M:%S')

  # Get the base factory bundle path if we are running using factory.par
  # inside a factory bundle.
  args.bundle_dir = common.GetEnclosingFactoryBundle() or None

  config = LoadConfig(board=args.board, filepath=args.file)
  runner = FactoryFlowRunner(config, output_dir=args.output_dir,
                             log_dir=args.log_dir, bundle_dir=args.bundle_dir)
  runner.RunTests(plan=args.plan, dut=args.dut, fail_fast=args.fail_fast)
  if args.clean_up:
    runner.CleanUp()


if __name__ == '__main__':
  main()
