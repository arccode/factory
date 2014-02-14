# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running automated factory tests on a DUT."""

import logging
import subprocess
import yaml

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import (
    board_cmd_arg, dut_hostname_cmd_arg, FactoryFlowCommand)
from cros.factory.goofy.goofy_rpc import RunState
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import utils
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
      CmdArg('--no-clear-states', dest='clear_states', action='store_false',
             default=True, help='do not clear factory test states and VPD'),
      CmdArg('--no-wait', dest='wait', action='store_false',
             help='do not wait for automated factory tests to complete'),
      CmdArg('--timeout-mins', type=float, default=60,
             help='minutes to wait before marking the test run as failed'),
  ]

  def Run(self):
    self.StartAutomatedTests()
    if self.options.wait:
      self.WaitForTestsToFinish()

  def StartAutomatedTests(self):
    """Enables automated tests on the DUT."""
    GOOFY_REMOTE = '/usr/local/factory/bin/goofy_remote'
    FACTORY_RESTART = '/usr/local/factory/bin/factory_restart'

    logging.info('Runing automated tests on %s', self.options.dut)
    if self.options.test_list:
      ssh_utils.SpawnSSHToDUT(
          [self.options.dut, GOOFY_REMOTE, self.options.dut,
           '--test_list=%s' % self.options.test_list, '--local'], log=True,
          check_call=True)
    ssh_utils.SpawnSSHToDUT(
        [self.options.dut, FACTORY_RESTART, '--automation-mode',
         '%s' % self.options.automation_mode] +
        (['-a', '-d'] if self.options.clear_states else []),
        log=True, check_call=True)

  def WaitForTestsToFinish(self):
    """Waits for the automated test run to finish."""
    # TODO(jcliang): Convert SSH + goofy_rpc to pure JSON RPC by creating a
    #                SSH tunnel to the DUT.
    WAIT_FOR_GOOFY_TIMEOUT_SECS = 60
    GOOFY_POLLING_INTERVAL = 3

    finished_tests = set()
    def WaitForGoofy():
      """Waits for Goofy to come up."""
      try:
        goofy_status = yaml.safe_load(ssh_utils.SpawnSSHToDUT(
            [self.options.dut, 'goofy_rpc', '"GetGoofyStatus()"'],
            check_output=True, ignore_stderr=True).stdout_data)
        return goofy_status['status'] == 'RUNNING'
      except Exception:
        return False

    # Wait for Goofy to come up.
    logging.info('Waiting for Goofy to come up')
    utils.WaitFor(WaitForGoofy, timeout_secs=WAIT_FOR_GOOFY_TIMEOUT_SECS,
                  poll_interval=GOOFY_POLLING_INTERVAL)
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
          [self.options.dut, 'goofy_rpc', '"GetTestRunStatus(None)"'],
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
          finished_tests.add(t)

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
                  poll_interval=GOOFY_POLLING_INTERVAL)
