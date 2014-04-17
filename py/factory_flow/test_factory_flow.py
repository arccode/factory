#!/usr/bin/python -Bu
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A tool for running factory flow tests."""

import glob
import logging
import os
import smtplib
import subprocess
import tempfile
import yaml
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import factory_common   # pylint: disable=W0611
from cros.factory.common import MakeList
from cros.factory.factory_flow import common
from cros.factory.hacked_argparse import CmdArg, ParseCmdline, verbosity_cmd_arg
from cros.factory.test import utils
from cros.factory.tools import build_board
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import ssh_utils


# Set default verbosity to INFO.
verbosity_cmd_arg[1]['default'] = logging.INFO

CONFIG_FILE_PATH_IN_CHROOT = lambda board: os.path.join(
    os.environ['CROS_WORKON_SRCROOT'], 'src', 'platform',
    'factory-private', 'board_testing_config',
    'board_config-%s.yaml' % board)
CONFIG_FILE_PATH_OUTSIDE_CHROOT = lambda board: (
    '/var/factory/board_config-%s.yaml' % board)

TestStatus = utils.Enum(['NOT_TESTED', 'PASSED', 'FAILED'])


class FactoryFlowTestError(Exception):
  """Factory flow runner error."""
  pass


class TestResult(object):
  """A class to hold test results of a test plan.

  Properties:
    board_name: The board name of the test plan.
    test_plan_name: The name of the test plan.
    test_plan_config: The configs of the test plan, as a dict.
    base_log_dir: The path to base log directory.
    results: The test results of each test item, stored in a per DUT basis.
  """
  def __init__(self, board_name, plan_name, plan_config, base_log_dir):
    self.board_name = build_board.BuildBoard(board_name)
    self.test_plan_name = plan_name
    self.test_plan_config = plan_config
    self.base_log_dir = base_log_dir
    self.results = {}
    # Initialize all items to NOT_TESTED.
    for dut in self.test_plan_config['dut']:
      self.results[dut] = {}
      for item in self.test_plan_config['test_sequence']:
        self.results[dut][item] = TestStatus.NOT_TESTED
      for item in self.test_plan_config['clean_up']:
        self.results[dut][item] = TestStatus.NOT_TESTED

  def SetTestItemResult(self, dut, item, status):
    """Sets the test result of a test item for the given DUT.

    Args:
      dut: The ID of the DUT.
      item: The ID of the test item.
      status: The status of the test item; must be one of TestStatus.
    """
    if not dut in self.test_plan_config['dut']:
      raise FactoryFlowTestError('DUT %r is not planned for %r' %
                                   (dut, self.test_plan_name))
    if not item in (self.test_plan_config['test_sequence'] +
                    self.test_plan_config['clean_up']):
      raise FactoryFlowTestError('Test item %r is not planned for %r' %
                                   (item, self.test_plan_name))
    self.results[dut][item] = status

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
    for d, item_status in self.results.iteritems():
      if all(s == TestStatus.PASSED for s in item_status.itervalues()):
        dut_status[d] = TestStatus.PASSED
      elif all(s == TestStatus.NOT_TESTED for s in item_status.itervalues()):
        dut_status[d] = TestStatus.NOT_TESTED
      elif any(s == TestStatus.FAILED for s in item_status.itervalues()):
        dut_status[d] = TestStatus.FAILED
      else:
        raise FactoryFlowTestError('Unexpected test status')
    if dut:
      return dut_status[dut]
    else:
      return (
          TestStatus.FAILED if any(
              s == TestStatus.FAILED for s in dut_status.itervalues())
          else TestStatus.PASSED)

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

    log_file_name = '%s.tar.bz2' % self.test_plan_name
    log_archive_path = os.path.join(self.base_log_dir, log_file_name)
    process_utils.Spawn(['tar', 'cJvf', log_file_name, self.test_plan_name],
                        cwd=self.base_log_dir, log=True, check_call=True)

    logging.info('Preparing notification E-mail...')
    report = []

    # Extract the bundle info from README in the testing bundle.
    upper_dir = os.path.dirname(self.base_log_dir)
    bundle_dir = glob.glob(os.path.join(
        upper_dir, 'factory_bundle_%s_*_testing' % self.board_name.full_name))
    if not bundle_dir:
      raise FactoryFlowTestError(
          ('Unable to locate the testing bundle directory; expect to find one '
           'bundle in %r') % upper_dir)
    if len(bundle_dir) > 1:
      raise FactoryFlowTestError(
          'Found %d bundles in %r; expect to find only one.' %
          (len(bundle_dir), upper_dir))
    readme = os.path.join(bundle_dir[0], 'README')
    if not os.path.exists(readme):
      raise FactoryFlowTestError('Unable to find README in %r' % bundle_dir[0])
    with open(readme) as f:
      report += [line.strip() for line in f.readlines()]

    # Generate overall test result of the test plan.
    overall_status = self.GetOverallTestResult()
    report += [
        '', '',
        '*** Overall test results: %-20s' % overall_status,
        '***',
        '*** Test result per DUT:',
        '***']

    # Generate overall test results and specific test result of each test item
    # for each DUT.
    for dut, result in self.results.iteritems():
      report += ['*** [%10s] %s' % (self.GetOverallTestResult(dut), dut)]
      for item in self.test_plan_config['test_sequence']:
        report += ['*** [%10s] - %s' % (result[item], item)]
      for item in self.test_plan_config['clean_up']:
        report += ['*** [%10s] - %s' % (result[item], item)]
      report += ['***']
    dut_results = MIMEText('\n'.join(report))

    # Generate log archive as a attachment to the E-mail.
    attachment = MIMEBase('application', 'octet-stream')
    with open(log_archive_path, 'rb') as f:
      attachment.set_payload(f.read())
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment',
                          filename=log_file_name)

    # Generate the notification E-mail.
    FROM = 'chromeos-factory-testing@chromium.org'
    mail = MIMEMultipart()
    mail['Subject'] = ('[%s] Test results and logs of %s on board %s' %
                       (overall_status, self.test_plan_name,
                        self.board_name.full_name))
    mail['To'] = ', '.join(self.test_plan_config['owners'])
    mail['From'] = FROM
    mail.attach(dut_results)
    mail.attach(attachment)

    logging.info('Sending notification E-mail to owners...')
    smtp = smtplib.SMTP('localhost')
    smtp.sendmail(FROM, self.test_plan_config['owners'], mail.as_string())
    smtp.quit()


class FactoryFlowRunner(object):
  """A class for running factory flow tests."""

  SUBCOMMANDS = ('create-bundle', 'start-server', 'usb-install',
                 'netboot-install', 'run-automated-tests')
  FACTORY_FLOW = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src',
                              'platform', 'factory', 'bin', 'factory_flow')

  def __init__(self, config, output_dir=None):
    self.config = config
    self.test_items = {}
    self.board = config['board']
    self.output_dir = output_dir or tempfile.mkdtemp(
        prefix='factory_flow_runner.')
    self.test_results = {}
    # Initialize log directory.
    self.log_dir = os.path.join(self.output_dir, 'logs')
    file_utils.TryMakeDirs(self.log_dir)

  def RunTests(self, plan=None, dut=None):
    """Runs the given test plan.

    Args:
      plan: The test plan to fun.  None to run all test plans.
      dut: The DUT to run factory flow tests on; this should be specified by the
        DUT ID in the config file.  None to test all DUT.
    """
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
      test_result = TestResult(self.board, plan, config, self.log_dir)

      if dut is not None:
        if dut not in config['dut']:
          logging.info('DUT %r is not planned for %r', dut, plan)
          continue
        dut_to_test = MakeList(dut)
      else:
        dut_to_test = config['dut']

      for d in dut_to_test:
        self.CreateTestItems(d)
        dut_info = self.config['dut_info'][d]
        log_dir = os.path.join(self.log_dir, plan, d)
        file_utils.TryMakeDirs(log_dir)

        test_env = os.environ.copy()
        test_env[common.BUNDLE_DIR_ENVVAR] = self.output_dir
        test_env[common.DUT_ENVVAR] = dut_info['ip']
        try:
          # Run through each test item; abort if any test item fails.
          item_under_test = None
          for item in config['test_sequence']:
            logging.info('Running test item %r on %r...', item, d)
            item_under_test = item
            command = self.test_items[d][item]
            process_utils.SpawnTee(
                command, log=True, env=test_env, check_call=True,
                output_file=os.path.join(log_dir, item + '.log'))
            test_result.SetTestItemResult(d, item_under_test, TestStatus.PASSED)
        except Exception:
          logging.exception('Test item failed')
          test_result.SetTestItemResult(d, item_under_test, TestStatus.FAILED)
        finally:
          try:
            self.GetLogsFromDUT(plan, d, log_dir)
          except subprocess.CalledProcessError:
            logging.exception('Unable to get factory logs from DUT')

          item_under_test = None
          # Run through each clean-up item; continue even if one fails.
          for item in config['clean_up']:
            try:
              logging.info('Running clean-up item %r on %r...', item, d)
              item_under_test = item
              command = self.test_items[d][item]
              process_utils.SpawnTee(
                  command, log=True, env=test_env, check_call=True,
                  output_file=os.path.join(log_dir, item + '.log'))
              test_result.SetTestItemResult(
                  d, item_under_test, TestStatus.PASSED)
            except Exception:
              logging.exception('Clean-up item failed')
              test_result.SetTestItemResult(d, item_under_test,
                                            TestStatus.FAILED)

      test_result.NotifyOwners()

  def CreateTestItems(self, dut):
    """Creates test items for the given DUT using its DUT info in the config.

    Args:
      dut: The DUT to create test items for; this should be specified by the DUT
        ID in the config file.
    """
    self.test_items[dut] = {}
    dut_info = self.config['dut_info'][dut]
    test_items = self.config['test_items']
    for key, args in test_items.iteritems():
      cmd_name = args['command']
      if cmd_name not in self.SUBCOMMANDS:
        raise FactoryFlowTestError('Invalid subcommand %r' % args['command'])

      args['board'] = self.board
      if cmd_name == 'create-bundle':
        args['output-dir'] = self.output_dir
        args['mini-omaha-ip'] = dut_info.get('host_ip')

      elif cmd_name == 'start-server':
        # Start a temporary DHCP server for the DUT.
        args['dhcp-iface'] = dut_info.get('dhcp_iface')
        args['host-ip'] = dut_info.get('host_ip')
        args['dut-mac'] = dut_info.get('eth_mac')
        args['dut-ip'] = dut_info.get('ip')

      elif cmd_name == 'usb-install':
        args['servo-host'] = dut_info.get('servo_host')
        args['servo-port'] = dut_info.get('servo_port')
        args['servo-serial'] = dut_info.get('servo_serial')

      elif cmd_name == 'netboot-install':
        args['servo-host'] = dut_info.get('servo_host')
        args['servo-port'] = dut_info.get('servo_port')
        args['servo-serial'] = dut_info.get('servo_serial')

      elif cmd_name == 'run-automated-tests':
        args['shopfloor-ip'] = dut_info.get('host_ip')
        args['shopfloor-port'] = dut_info.get('shopfloor_port')
        if args['test-list'] in dut_info.get('test_list_customization', []):
          # Generate YAML files and set up automation environment on the DUT.
          def CreateTempYAMLFile(suffix, data):
            filename = os.path.join(
                self.output_dir,
                '%s-%s-%s.yaml' % (dut, args['test-list'], suffix))
            with open(filename, 'w') as f:
              f.write(yaml.safe_dump(data))
            return filename

          settings = dut_info['test_list_customization'][args['test-list']]
          for item in ('device_data', 'vpd', 'test_list_dargs',
                       'automation_function_kwargs'):
            data = settings.get(item)
            if data:
              args[item.replace('_', '-') + '-yaml'] = CreateTempYAMLFile(
                  item, data)

      command_args = [self.FACTORY_FLOW, cmd_name]
      for name, value in args.iteritems():
        if name == 'command' or value is None:
          continue
        if isinstance(value, bool) and value:
          command_args += ['--%s' % name]
        else:
          command_args += ['--%s=%s' % (name, value)]

      self.test_items[dut][key] = command_args

  def GetLogsFromDUT(self, plan, dut, output_path):
    """Gets factory logs from the DUT.

    Args:
      plan: The ID of the test plan; used to name the log archive.
      dut: The ID of the DUT to get factory logs from.
      output_path: The output path of the log archive.
    """
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
      verbosity_cmd_arg
  ]
  args = ParseCmdline('Factory flow runner', *arguments)
  logging.basicConfig(
      format=('[%(levelname)s] factory_flow ' +
              '%(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=args.verbosity, datefmt='%Y-%m-%d %H:%M:%S')

  config = LoadConfig(board=args.board, filepath=args.file)
  FactoryFlowRunner(config, output_dir=args.output_dir).RunTests(
      plan=args.plan, dut=args.dut)


if __name__ == '__main__':
  main()
