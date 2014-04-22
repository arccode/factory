# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running automated factory tests on a DUT."""

import logging
import os
import subprocess
import yaml

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import (
    board_cmd_arg, dut_hostname_cmd_arg, FactoryFlowCommand)
from cros.factory.goofy.goofy_rpc import RunState
from cros.factory.goofy.invocation import OVERRIDE_TEST_LIST_DARGS_FILE
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import utils
from cros.factory.test.e2e_test.automator import AUTOMATION_FUNCTION_KWARGS_FILE
from cros.factory.utils import ssh_utils


TEST_AUTOMATION_MESSAGE = """
*** Start factory test automation on DUT %(dut)s:
***   - Automation mode: %(automation_mode)s
***   - Test list: %(test_list)s
***   - Clear state: %(clear_states)s
"""


class RunAutomatedTestsError(Exception):
  """Run automated test error."""
  pass


class RunAutomatedTests(FactoryFlowCommand):
  """Runs automated factory tests on DUT."""
  args = [
      board_cmd_arg,
      dut_hostname_cmd_arg,
      CmdArg('--automation-mode', choices=['none', 'partial', 'full'],
             default='partial', help=(
                 'mode of factory test automation to enable '
                 '(default: %(default)s)')),
      CmdArg('--test-list', default=None, help='test list to run'),
      CmdArg('--shopfloor-ip', help='IP of shop floor server'),
      CmdArg('--shopfloor-port', type=int, help='port of shop floor server'),
      CmdArg('--no-clear-states', dest='clear_states', action='store_false',
             default=True, help='do not clear factory test states and VPD'),
      CmdArg('--no-wait', dest='wait', action='store_false',
             help='do not wait for automated factory tests to complete'),
      CmdArg('--run', help='run only the specified factory test'),
      CmdArg('--timeout-mins', type=float, default=60,
             help='minutes to wait before marking the test run as failed'),
      CmdArg('--device-data-yaml',
             help=('a YAML file containing a dict of device data '
                   'key-value pairs to set on the DUT')),
      CmdArg('--vpd-yaml',
             help=('a YAML file containing a dict of RO and RW VPD '
                   'key-value pairs to set on the DUT')),
      CmdArg('--test-list-dargs-yaml',
             help=('a YAML file containing a dict of test paths to '
                   'their override dargs')),
      CmdArg('--automation-function-kwargs-yaml',
             help=('a YAML file containing a dict of test paths to '
                   'their kwargs for their automation functions')),
  ]

  WAIT_FOR_GOOFY_TIMEOUT_SECS = 60
  SSH_CONNECT_TIMEOUT = 3
  GOOFY_POLLING_INTERVAL = 5

  def Run(self):
    self.EnableFactoryTestAutomation()
    self.WaitForGoofy()
    self.PrepareAutomationEnvironment()
    self.StartAutomatedTests()
    if self.options.wait:
      self.WaitForTestsToFinish()

  def PrepareAutomationEnvironment(self):
    """Prepares settings for factory test automation on the DUT."""
    def _CheckFile(path):
      if not os.path.exists(path):
        raise RunAutomatedTestsError('Unable to locate file %r' % path)

    if self.options.device_data_yaml:
      # Rsyncs the device data YAML file to the DUT and loads it.
      _CheckFile(self.options.device_data_yaml)
      TEMP_DEVICE_DATA_PATH = '/tmp/device_data'
      DUT_FACTORY_BIN = '/usr/local/factory/bin/factory'

      ssh_utils.SpawnRsyncToDUT(
          [self.options.device_data_yaml,
           '%s:%s' % (self.options.dut, TEMP_DEVICE_DATA_PATH)],
          log=True, check_call=True)
      ssh_utils.SpawnSSHToDUT(
          [self.options.dut, DUT_FACTORY_BIN, 'device-data', '--set-yaml',
           TEMP_DEVICE_DATA_PATH], log=True, check_call=True)

    if self.options.vpd_yaml:
      _CheckFile(self.options.vpd_yaml)
      with open(self.options.vpd_yaml) as f:
        vpd_yaml_dict = yaml.safe_load(f.read())

      def GenerateVPDSetterArgs(vpd_dict):
        result = []
        for key, value in vpd_dict.iteritems():
          result.extend(['-s', '"%s"="%s"' % (key, value)])
        return result

      vpd_section_args = {
          'ro': 'RO_VPD',
          'rw': 'RW_VPD',
      }
      for section in ('ro', 'rw'):
        vpd_setters = GenerateVPDSetterArgs(vpd_yaml_dict[section])
        ssh_utils.SpawnSSHToDUT(
            [self.options.dut, 'vpd', '-i', vpd_section_args[section]] +
            vpd_setters,
            log=True, check_call=True)

    if self.options.test_list_dargs_yaml:
      # Rsyncs the test list dargs YAML file to the DUT.
      _CheckFile(self.options.test_list_dargs_yaml)
      TEMP_DARGS_PATH = '/tmp/test_list_dargs'
      DUT_DARGS_PATH = os.path.join(
          '/var/factory/state/',
          os.path.basename(OVERRIDE_TEST_LIST_DARGS_FILE))

      ssh_utils.SpawnRsyncToDUT(
          [self.options.test_list_dargs_yaml,
           '%s:%s' % (self.options.dut, TEMP_DARGS_PATH)],
          log=True, check_call=True)
      ssh_utils.SpawnSSHToDUT(
          [self.options.dut, 'mv', TEMP_DARGS_PATH, DUT_DARGS_PATH],
          log=True, check_call=True)

    if self.options.automation_function_kwargs_yaml:
      # Rsyncs the automation function kwargs YAML file to the DUT.
      _CheckFile(self.options.automation_function_kwargs_yaml)
      TEMP_KWARGS_PATH = '/tmp/automation_function_kwargs'
      DUT_KWARGS_PATH = os.path.join(
          '/var/factory/state/',
          os.path.basename(AUTOMATION_FUNCTION_KWARGS_FILE))

      ssh_utils.SpawnRsyncToDUT(
          [self.options.automation_function_kwargs_yaml,
           '%s:%s' % (self.options.dut, TEMP_KWARGS_PATH)],
          log=True, check_call=True)
      ssh_utils.SpawnSSHToDUT(
          [self.options.dut, 'mv', TEMP_KWARGS_PATH, DUT_KWARGS_PATH],
          log=True, check_call=True)

  def EnableFactoryTestAutomation(self):
    """Enables factory test automation on the DUT."""
    GOOFY_REMOTE = '/usr/local/factory/bin/goofy_remote'
    FACTORY_RESTART = '/usr/local/factory/bin/factory_restart'

    logging.info('Runing automated tests on %s', self.options.dut)
    goofy_remote_args = [self.options.dut, GOOFY_REMOTE, self.options.dut,
                         '--local']
    if self.options.test_list:
      goofy_remote_args += ['--test_list=%s' % self.options.test_list]
    if self.options.shopfloor_ip:
      goofy_remote_args += ['-s', self.options.shopfloor_ip]
    if self.options.shopfloor_port:
      goofy_remote_args += ['--shopfloor_port=%s', self.options.shopfloor_port]
    ssh_utils.SpawnSSHToDUT(goofy_remote_args, log=True, check_call=True)
    ssh_utils.SpawnSSHToDUT(
        [self.options.dut, FACTORY_RESTART, '--automation-mode',
         '%s' % self.options.automation_mode, '--no-auto-run-on-start'] +
        (['-a', '-d'] if self.options.clear_states else []),
        log=True, check_call=True)

  def WaitForGoofy(self):
    """Waits for Goofy to come up."""
    def PollGoofy():
      try:
        goofy_status = yaml.safe_load(ssh_utils.SpawnSSHToDUT(
            ['-o', 'ConnectTimeout=%d' % self.SSH_CONNECT_TIMEOUT,
             self.options.dut, 'goofy_rpc', '"GetGoofyStatus()"'],
            check_output=True, ignore_stderr=True).stdout_data)
        return goofy_status['status'] == 'RUNNING'
      except Exception:
        return False

    # Wait for Goofy to come up.
    logging.info('Waiting for Goofy to come up')
    utils.WaitFor(PollGoofy, timeout_secs=self.WAIT_FOR_GOOFY_TIMEOUT_SECS,
                  poll_interval=self.GOOFY_POLLING_INTERVAL)

  def StartAutomatedTests(self):
    """Starts automated factory tests."""
    if self.options.run:
      ssh_utils.SpawnSSHToDUT(
          [self.options.dut, 'goofy_rpc "RunTest(\'%s\')"' % self.options.run])
    else:
      ssh_utils.SpawnSSHToDUT(
          [self.options.dut, 'goofy_rpc "RestartAllTests()"'],
          log=True, check_call=True)

  def WaitForTestsToFinish(self):
    """Waits for the automated test run to finish."""
    # TODO(jcliang): Convert SSH + goofy_rpc to pure JSON RPC by creating a
    #                SSH tunnel to the DUT.
    finished_tests = []

    test_list = ssh_utils.SpawnSSHToDUT(
        [self.options.dut, 'factory', 'test-list'],
        check_output=True).stdout_data.strip()
    print TEST_AUTOMATION_MESSAGE % dict(
        dut=self.options.dut,
        automation_mode=self.options.automation_mode,
        test_list=test_list,
        clear_states=self.options.clear_states)

    def FetchRunStatus():
      """Fetches run status on the DUT through Goofy RPC."""
      run_status = ssh_utils.SpawnSSHToDUT(
          ['-o', 'ConnectTimeout=%d' % self.SSH_CONNECT_TIMEOUT,
           self.options.dut, 'goofy_rpc', '"GetTestRunStatus(None)"'],
          check_output=True, ignore_stderr=True).stdout_data
      return yaml.safe_load(run_status)

    def ParseFinishedTests(run_status):
      """Parses finish tests."""
      finished = [
          (t['path'], t['status']) for t in run_status['scheduled_tests']
          if t['status'] in ('PASSED', 'FAILED')]
      for t in finished:
        if t not in finished_tests:
          logging.info('[%s] %s', t[1], t[0])
          finished_tests.append(t)

    def WaitForRun():
      """Waits for test run to finish."""
      try:
        run_status = FetchRunStatus()
        ParseFinishedTests(run_status)
        return run_status['status'] == RunState.FINISHED
      except subprocess.CalledProcessError:
        # Cannot SSH into the DUT; probably a reboot test is running.
        return False

    logging.info('Waiting for automated test run to finish')
    utils.WaitFor(WaitForRun, timeout_secs=self.options.timeout_mins * 60,
                  poll_interval=self.GOOFY_POLLING_INTERVAL)

    if not finished_tests:
      raise RunAutomatedTestsError('No test was run')

    failed_tests = [t[0] for t in finished_tests if t[1] == 'FAILED']
    if failed_tests:
      raise RunAutomatedTestsError(
          'The following tests failed:' + '\n'.join(failed_tests))
