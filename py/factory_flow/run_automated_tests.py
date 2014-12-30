# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running automated factory tests on a DUT."""

from __future__ import print_function

import glob
import httplib
import jsonrpclib
import logging
import os
import socket
import subprocess
import threading
import time
import yaml

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import (
    board_cmd_arg, bundle_dir_cmd_arg, dut_hostname_cmd_arg, FactoryFlowCommand)
from cros.factory.goofy import connection_manager
from cros.factory.goofy import goofy_remote
from cros.factory.goofy.goofy_rpc import RunState
from cros.factory.goofy.invocation import OVERRIDE_TEST_LIST_DARGS_FILE
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import state
from cros.factory.test.e2e_test.automator import AUTOMATION_FUNCTION_KWARGS_FILE
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import ssh_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


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
      bundle_dir_cmd_arg,
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
      CmdArg('--run', metavar='TEST_PATH',
             help='run only the specified factory test'),
      CmdArg('--timeout-mins', type=float, default=60,
             help='minutes to wait before marking the test run as failed'),
      CmdArg('--log-dir',
             help=('path to the directory to store factory logs from DUT; '
                   'defaults to <output_dir>/logs/factory_logs')),
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
      CmdArg('--role', choices=goofy_remote.HOST_BASED_ROLES.keys(),
             help='the host-based role to enable on the DUT'),
  ]

  WAIT_FOR_GOOFY_TIMEOUT_SECS = 120
  GOOFY_POLLING_INTERVAL = 5

  ssh_tunnel = None

  def Init(self):
    if not self.options.log_dir:
      self.options.log_dir = os.path.join(self.options.bundle, os.path.pardir,
                             'logs', 'factory_logs')
    file_utils.TryMakeDirs(self.options.log_dir)

  def Run(self):
    self.EnableFactoryTestAutomation()
    self.RebootDUT()
    self.WaitForGoofy()
    self.PrepareAutomationEnvironment()
    self.StartAutomatedTests()
    if self.options.wait:
      self.WaitForTestsToFinish()

  def TearDown(self):
    if self.ssh_tunnel:
      self.ssh_tunnel.Close()

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
      goofy_remote_args += ['--shopfloor_port=%s' % self.options.shopfloor_port]
    if self.options.role:
      goofy_remote_args += ['--role=%s' % self.options.role]
    ssh_utils.SpawnSSHToDUT(goofy_remote_args, log=True, check_call=True)
    ssh_utils.SpawnSSHToDUT(
        [self.options.dut, FACTORY_RESTART, '--automation-mode',
         '%s' % self.options.automation_mode, '--no-auto-run-on-start'] +
        (['-a', '-d'] if self.options.clear_states else []),
        log=True, check_call=True)

  def RebootDUT(self):
    """Reboots the DUT.

    We often need to reboot the DUT in order for some changes to take effect.
    For example, if we switch the goofy operation mode (host-based v.s.
    DUT-only), we will need to reboot the DUT to enable the new mode.
    """
    ssh_utils.SpawnSSHToDUT([self.options.dut, 'sync && reboot'],
                            log=True, check_call=True)

  def GetGoofyProxy(self):
    """Creates a Goofy RPC proxy.

    A SSH tunnel to DUT is created each time this function is called. This is to
    ensure that the tunnel is alive, since DUT can go through reboot test and
    make established tunnel unreachable. If a SSH tunnel has been established
    then the tunnel will be closed before a new one is established.

    Returns:
      A Goofy RPC proxy instance, or None if the method fails to create a proxy.
    """
    try:
      if self.ssh_tunnel:
        self.ssh_tunnel.Close()
      # Ping the host first to make sure it is up.
      sync_utils.WaitFor(
          lambda: connection_manager.PingHost(self.options.dut, timeout=1) == 0,
          timeout_secs=30)
      # Create a SSH tunnel to connect to the JSON RPC server on DUT.
      local_port = net_utils.GetUnusedPort()
      self.ssh_tunnel = ssh_utils.SSHTunnelToDUT(
          self.options.dut, local_port, state.DEFAULT_FACTORY_STATE_PORT)
      self.ssh_tunnel.Establish()
      goofy_proxy = state.get_instance(
          address=net_utils.LOCALHOST, port=local_port)
      goofy_proxy.GetGoofyStatus()  # Make sure the proxy works.
      return goofy_proxy
    except (type_utils.TimeoutError,        # Cannot ping DUT.
            subprocess.CalledProcessError,  # Cannot create SSH tunnel.
            socket.error,                   # Cannot connect to Goofy on DUT.
            httplib.BadStatusLine):         # Goofy RPC on DUT is not ready.
      return None

  def WaitForGoofy(self):
    """Waits for Goofy to come up."""
    def PollGoofy():
      goofy_proxy = self.GetGoofyProxy()
      if goofy_proxy is None:
        return False
      return goofy_proxy.GetGoofyStatus()['status'] == 'RUNNING'

    logging.info('Waiting for Goofy to come up')
    sync_utils.WaitFor(PollGoofy, timeout_secs=self.WAIT_FOR_GOOFY_TIMEOUT_SECS,
                       poll_interval=self.GOOFY_POLLING_INTERVAL)

  def StartAutomatedTests(self):
    """Starts automated factory tests."""
    goofy_proxy = self.GetGoofyProxy()
    if goofy_proxy is None:
      raise RunAutomatedTestsError('Unable to connect to Goofy on DUT')
    if self.options.run:
      goofy_proxy.RunTest(self.options.run)
    else:
      goofy_proxy.RestartAllTests()

  def WaitForTestsToFinish(self):
    """Waits for the automated test run to finish."""
    finished_tests = []
    goofy_proxy = self.GetGoofyProxy()
    if goofy_proxy is None:
      raise RunAutomatedTestsError('Unable to connect to Goofy on DUT')
    test_list = goofy_proxy.GetGoofyStatus()['test_list_id']
    stop_event = threading.Event()

    def KeepSyncingFactoryLogs(stop_event):
      """Keeps syncing factory logs from the DUT to the host."""
      per_test_list_log_dir = os.path.join(self.options.log_dir, test_list)
      file_utils.TryMakeDirs(per_test_list_log_dir)
      while not stop_event.is_set():
        ssh_utils.SpawnRsyncToDUT(
            ['-aP', '%s:/var/factory' % self.options.dut,
             per_test_list_log_dir],
            stdout=process_utils.OpenDevNull(),
            stderr=process_utils.OpenDevNull(),
            call=True)
        time.sleep(1)

    # Start a thread to keep syncing factory logs from the DUT.
    sync_log_thread = threading.Thread(target=KeepSyncingFactoryLogs,
                                       args=(stop_event,))
    sync_log_thread.start()

    print(TEST_AUTOMATION_MESSAGE % dict(
        dut=self.options.dut,
        automation_mode=self.options.automation_mode,
        test_list=test_list,
        clear_states=self.options.clear_states))

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
      goofy_proxy = self.GetGoofyProxy()
      if goofy_proxy is None:
        # Cannot connect to DUT; probably a reboot/suspend test is running,
        # or DUT is finalized.
        finalize_report_spec = glob.glob(
            os.path.join(self.options.bundle, 'shopfloor', 'shopfloor_data',
                         'reports', time.strftime('logs.%Y%m%d'), '*.tar.xz'))
        if finalize_report_spec:
          logging.info(('Found finalize report %s; assuming DUT has been '
                        'finalized'), finalize_report_spec[0])
          return True
        return False
      try:
        # Fetch run status on the DUT through Goofy RPC.
        run_status = goofy_proxy.GetTestRunStatus(None)
      except (jsonrpclib.jsonrpc.ProtocolError, socket.error,
              httplib.BadStatusLine):
        # Time out waiting for response from Goofy RPC, or the SSH connection is
        # gone.
        return False
      ParseFinishedTests(run_status)
      return run_status['status'] in (RunState.FINISHED,
                                      RunState.NOT_ACTIVE_RUN)

    try:
      logging.info('Waiting for automated test run to finish')
      sync_utils.WaitFor(WaitForRun,
                         timeout_secs=self.options.timeout_mins * 60,
                         poll_interval=self.GOOFY_POLLING_INTERVAL)

      if not finished_tests:
        raise RunAutomatedTestsError('No test was run')

      failed_tests = [t[0] for t in finished_tests if t[1] == 'FAILED']
      if failed_tests:
        raise RunAutomatedTestsError(
            'The following test(s) failed:' + '\n'.join(failed_tests))
    finally:
      stop_event.set()
      sync_log_thread.join()
