# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The finalize test is the last step before DUT switching to release image.

The test checks if all tests are passed, and checks the hardware
write-protection, charge percentage. Then it invoke gooftool finalize with
specified arguments to switch the machine to release image.
"""


import json
import logging
import os
import random
import re
import subprocess
import threading
import time
import unittest

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device.links import ssh
from cros.factory.test.env import paths
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test import gooftools
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.rules import phase
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import deploy_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


MSG_CHECKING = i18n_test_ui.MakeI18nLabel(
    'Checking system status for finalization...')
MSG_NOT_READY = i18n_test_ui.MakeI18nLabel(
    'System is not ready.<br>'
    'Please fix RED tasks and then press SPACE.')
MSG_NOT_READY_POLLING = i18n_test_ui.MakeI18nLabel(
    'System is NOT ready. Please fix RED tasks.')
MSG_FORCE = i18n_test_ui.MakeI18nLabel(
    'Press "f" to force starting finalization procedure.')
MSG_READY = i18n_test_ui.MakeI18nLabel(
    'System is READY. Press SPACE to start FINALIZATION.')
MSG_FINALIZING = i18n_test_ui.MakeI18nLabel(
    'Finalizing, please wait.<br>'
    'Do not restart the device or terminate this test,<br>'
    'or the device may become unusable.')


class Finalize(unittest.TestCase):
  """The main class for finalize pytest."""
  ARGS = [
      Arg('write_protection', bool,
          'Check write protection.', default=True),
      Arg('polling_seconds', (int, type(None)),
          'Interval between updating results (None to disable polling).',
          default=5),
      Arg('allow_force_finalize', list,
          'List of users as strings allowed to force finalize, supported '
          'users are operator or engineer.',
          default=['operator', 'engineer']),
      Arg('min_charge_pct', int,
          'Minimum battery charge percentage allowed (None to disable '
          'checking charge level)',
          optional=True),
      Arg('max_charge_pct', int,
          'Maximum battery charge percentage allowed (None to disable '
          'checking charge level)',
          optional=True),
      Arg('secure_wipe', bool,
          'Wipe the stateful partition securely (False for a fast wipe).',
          default=True),
      Arg('upload_method', str,
          'Upload method for "gooftool finalize"',
          optional=True),
      Arg('waive_tests', list,
          'Do not require certain tests to pass.  This is a list of elements; '
          'each element must either be a regular expression of test path, '
          'or a tuple of regular expression of test path and a regular '
          'expression that must match the error message in order to waive the '
          'test. If regular expression of error message is empty, the test '
          'can be waived if it is either UNTESTED or FAILED. '
          r'e.g.: [(r"^FATP\.FooBar$", r"Timeout"), (r"Diagnostic\..*")] will '
          'waive FATP.FooBar test if error message starts with Timeout. It '
          'will also waive all Diagnostic.* tests, either UNTESTED or FAILED. '
          'Error messages may be multiline (e.g., stack traces) so this is a '
          'multiline match.  This is a Python re.match operation, so it will '
          'match from the beginning of the error string.',
          default=[]),
      Arg('untested_tests', list,
          'A list of tests that should not be tested at this point, e.g. test '
          'cases which, by design, will be run AFTER finalization. To prevent '
          'test being added to this list by accident, each element must be'
          'a exact test path, rather than a regular expression.',
          default=[]),
      Arg('enable_shopfloor', bool,
          'Perform shopfloor operations: update HWID data and flush event '
          'logs.', default=True),
      Arg('sync_event_logs', bool, 'Sync event logs to shopfloor',
          default=True),
      Arg('rma_mode', bool,
          'Enable rma_mode, do not check for deprecated components.',
          default=False, optional=True),
      Arg('is_cros_core', bool,
          'For ChromeOS Core device, skip verifying branding and setting'
          'firmware bitmap locale.',
          default=False, optional=True),
      Arg('inform_shopfloor_after_wipe', bool,
          'Inform shopfloor server that the device is finalized after it gets'
          'wiped. For in-place wipe, it is recommended to set to True so'
          'a shopfloor call can be made AFTER device gets wiped successfully.'
          'For legacy wipe, shopfloor call is always made before wiping.',
          default=True),
      Arg('enforced_release_channels', list,
          'A list of string indicating the enforced release image channels. '
          'Each item should be one of "dev", "beta" or "stable".',
          default=None, optional=True),
      Arg('use_local_gooftool', bool,
          'If DUT is local, use factory.par or local gooftool? If DUT is not '
          'local, factory.par is always used.', default=True, optional=True),
      Arg('station_ip', str,
          'IP address of this station.', default=None, optional=True),
      Arg('gooftool_waive_list', list,
          'A list of waived checks for "gooftool finalize", '
          'see "gooftool finalize --help" for available items.',
          default=[], optional=True),
      Arg('gooftool_skip_list', list,
          'A list of skipped checks for "gooftool finalize", '
          'see "gooftool finalize --help" for available items.',
          default=[], optional=True),
      ]

  FINALIZE_TIMEOUT = 180

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.force = False
    self.go_cond = threading.Condition()
    self.test_states_path = os.path.join(paths.DATA_LOG_DIR, 'test_states')
    self.factory_par = deploy_utils.CreateFactoryTools(self.dut)

    # variables for remote SSH DUT
    self.dut_response = None
    self.response_listener = None

    # Set of waived tests.
    self.waived_tests = set()

    # Normalize 0 to None (since various things, e.g.,
    # Condition.wait(timeout), treat 0 and None differently.
    if self.args.polling_seconds == 0:
      self.args.polling_seconds = None

  def tearDown(self):
    if self.response_listener:
      self.response_listener.shutdown()
      self.response_listener.server_close()
      self.response_listener = None

  def runTest(self):
    # Check waived_tests argument.  (It must be empty at DVT and
    # beyond.)
    phase.AssertStartingAtPhase(
        phase.DVT,
        not self.args.waive_tests,
        'Tests may not be waived; set of waived tests is %s' % (
            self.args.waive_tests))

    phase.AssertStartingAtPhase(phase.PVT, self.args.write_protection,
                                'Write protection must be enabled')

    # Check for HWID bundle update from shopfloor.
    if self.args.enable_shopfloor:
      shopfloor.update_local_hwid_data(self.dut)

    # Preprocess waive_tests: turn it into a list of tuples where the
    # first element is the regular expression of test id and the second
    # is the regular expression of error messages.
    for i, w in enumerate(self.args.waive_tests):
      if isinstance(w, str):
        w = (w, '')  # '' matches anything
      self.assertTrue(isinstance(w, tuple) and
                      len(w) == 2,
                      'Invalid waive_tests element %r' % (w,))
      self.args.waive_tests[i] = (re.compile(w[0]),
                                  re.compile(w[1], re.MULTILINE))

    test_list = self.test_info.ReadTestList()
    test_states = test_list.AsDict(
        state.get_instance().get_test_states())

    file_utils.TryMakeDirs(os.path.dirname(self.test_states_path))
    with open(self.test_states_path, 'w') as f:
      yaml.dump(test_states, f)

    event_log.Log('test_states', test_states=test_states)

    def Go(force=False):
      with self.go_cond:
        if self.ForcePermissions():
          self.force = force
        self.go_cond.notify()
    self.ui.BindKey(test_ui.SPACE_KEY, lambda _: Go(False))
    self.ui.BindKey('F', lambda _: Go(True))

    thread = threading.Thread(target=self.Run)

    # Set this thread as daemon thread so once in-place wipe kill factory
    # service, finalize.py is terminated to release the resources.
    thread.setDaemon(True)
    thread.start()
    self.ui.Run()

  def Run(self):
    try:
      self.LogImageVersion()
      self.RunPreflight()
      self.template.SetState(MSG_FINALIZING)
      self.DoFinalize()
    except Exception as e:
      self.ui.Fail('Exception during finalization: %s' % e)

  def LogImageVersion(self):
    release_image_version = self.dut.info.release_image_version
    factory_image_version = self.dut.info.factory_image_version
    if release_image_version:
      logging.info('release image version: %s', release_image_version)
    else:
      self.ui.Fail('Can not determine release image version')
    if factory_image_version:
      logging.info('factory image version: %s', factory_image_version)
    else:
      self.ui.Fail('Can not determine factory image version')
    event_log.Log('finalize_image_version',
                  factory_image_version=factory_image_version,
                  release_image_version=release_image_version)

  def _CallGoofTool(self, command):
    """Execute a gooftool command, `command`.

    Args:
      command: a string object which starts with 'gooftool '.
    """
    assert command.startswith('gooftool ')

    if self.dut.link.IsLocal() and self.args.use_local_gooftool:
      (out, unused_err, returncode) = gooftools.run(command)
      # since STDERR is logged, we only need to log STDOUT
      factory.console.info('========= STDOUT ========')
      factory.console.info(out)
    else:
      factory.console.info('call factory.par: %s', command)
      factory.console.info('=== STDOUT and STDERR ===')
      # append STDOUT and STDERR to console log.
      console_log_path = paths.CONSOLE_LOG_PATH
      file_utils.TryMakeDirs(os.path.dirname(console_log_path))
      with open(console_log_path, 'a') as output:
        returncode = self.factory_par.Call(command, stdout=output,
                                           stderr=subprocess.STDOUT)
    factory.console.info('=========================')
    factory.console.info('return code: %d', returncode)
    return returncode == 0

  def RunPreflight(self):
    def CheckRequiredTests():
      """Returns True if all tests (except waived tests) have passed."""
      test_list = self.test_info.ReadTestList()
      state_map = state.get_instance().get_test_states()

      self.waived_tests = set()

      for k, v in state_map.iteritems():
        test = test_list.LookupPath(k)
        if not test:
          # Test has been removed (e.g., by updater).
          continue

        if test.subtests:
          # There are subtests.  Don't check the parent itself (only check
          # the children).
          continue

        if v.status == factory.TestState.FAILED_AND_WAIVED:
          # The test is explicitly waived in the test list.
          continue

        if v.status == factory.TestState.UNTESTED:
          if k in self.args.untested_tests:
            # this is expected
            continue

          # See if it's been waived. The regular expression of error messages
          # must be empty string.
          for regex_path, regex_error_msg in self.args.waive_tests:
            if regex_path.match(k) and not regex_error_msg.pattern:
              self.waived_tests.add(k)
              logging.info('Waived UNTESTED test %r', k)
              break
          else:
            # It has not been waived.
            return False

        if v.status == factory.TestState.FAILED:
          # See if it's been waived.
          for regex_path, regex_error_msg in self.args.waive_tests:
            if regex_path.match(k) and regex_error_msg.match(v.error_msg):
              self.waived_tests.add(k)
              logging.info('Waived FAILED test %r', k)
              break
          else:
            # It has not been waived.
            return False

      return True

    def CheckDevSwitch():
      return self._CallGoofTool('gooftool verify_switch_dev')

    items = [(CheckRequiredTests,
              i18n_test_ui.MakeI18nLabel('Verify all tests passed')),
             (CheckDevSwitch,
              i18n_test_ui.MakeI18nLabel('Turn off Developer Switch'))]

    if self.args.write_protection:
      def CheckWriteProtect():
        return self._CallGoofTool('gooftool verify_switch_wp')

      items += [(CheckWriteProtect,
                 i18n_test_ui.MakeI18nLabel('Enable write protection pin'))]

    self.template.SetState(
        '<table style="margin: auto; font-size: 150%"><tr><td>' +
        '<div id="finalize-state">%s</div>' % MSG_CHECKING +
        '<table style="margin: auto"><tr><td>' +
        '<ul id="finalize-list" style="margin-top: 1em">' +
        ''.join('<li id="finalize-%d">%s' % (i, item[1])
                for i, item in enumerate(items)),
        '</ul>'
        '</td></tr></table>'
        '</td></tr></table>')

    def UpdateState():
      """Polls and updates the states of all checklist items.

      Returns:
        True if all have passed.
      """
      all_passed = True
      js = []
      for i, item in enumerate(items):
        try:
          passed = item[0]()
        except Exception:
          logging.exception('Error evaluating finalization condition')
          passed = False
        js.append('$("finalize-%d").className = "test-status-%s"' % (
            i, 'passed' if passed else 'failed'))
        all_passed = all_passed and passed

      self.ui.RunJS(';'.join(js))
      if not all_passed:
        msg = (MSG_NOT_READY_POLLING if self.args.polling_seconds
               else MSG_NOT_READY)
        if self.ForcePermissions():
          msg += '<div>' + MSG_FORCE + '</div>'
        self.ui.SetHTML(msg, id='finalize-state')

      return all_passed

    with self.go_cond:
      first_time = True
      while not self.force:
        if UpdateState():
          # All done!
          if first_time and not self.args.polling_seconds:
            # Succeeded on the first try, and we're not polling; wait
            # for a SPACE keypress.
            self.ui.SetHTML(MSG_READY, id='finalize-state')
            self.go_cond.wait()
          return

        # Wait for a "go" signal, up to polling_seconds (or forever if
        # not polling).
        self.go_cond.wait(self.args.polling_seconds)
        first_time = False

  def Warn(self, message, times=3):
    """Alerts user that a required test is bypassed."""
    for i in range(times, 0, -1):
      factory.console.warn(
          '%s. '
          'THIS DEVICE CANNOT BE QUALIFIED. '
          '(will continue in %d seconds)', message, i)
      time.sleep(1)

  def ForcePermissions(self):
    """Return true if there are permissions to force, false if not."""
    for user in self.args.allow_force_finalize:
      self.assertTrue(user in ['engineer', 'operator'],
                      'Invalid user %r in allow_force_finalize.' % user)
      if user == 'engineer' and self.ui.InEngineeringMode():
        return True
      elif user == 'operator' and not self.ui.InEngineeringMode():
        return True
    return False

  def NormalizeUploadMethod(self, method):
    """Builds the report file name and resolves variables."""
    if method in [None, 'none']:
      # gooftool accepts only 'none', not empty string.
      return 'none'

    if method == 'shopfloor':
      method = 'shopfloor:%s#%s' % (shopfloor.get_server_url(),
                                    state.GetSerialNumber())
    logging.info('Using upload method %s', method)

    return method

  def DoFinalize(self):
    upload_method = self.NormalizeUploadMethod(self.args.upload_method)

    command = 'gooftool -v 4 finalize'
    if self.waived_tests:
      self.Warn('TESTS WERE WAIVED: %s.' % sorted(list(self.waived_tests)))
    event_log.Log('waived_tests', waived_tests=sorted(list(self.waived_tests)))

    if self.args.enable_shopfloor and self.args.sync_event_logs:
      state.get_instance().FlushEventLogs()

    if not self.args.write_protection:
      self.Warn('WRITE PROTECTION IS DISABLED.')
      command += ' --no_write_protect'
    if not self.args.secure_wipe:
      command += ' --fast'

    if self.args.inform_shopfloor_after_wipe and shopfloor.is_enabled():
      server_url = shopfloor.get_server_url()
      if server_url:
        command += ' --shopfloor_url "%s"' % server_url

    command += ' --upload_method "%s"' % upload_method
    command += ' --add_file "%s"' % self.test_states_path
    if self.args.rma_mode:
      command += ' --rma_mode'
      logging.info('Using RMA mode. Accept deprecated components')
    if self.args.is_cros_core:
      command += ' --cros_core'
      logging.info('ChromeOS Core device. Skip some check.')
    if self.args.enforced_release_channels:
      command += ' --enforced_release_channels %s' % (
          ' '.join(self.args.enforced_release_channels))
      logging.info(
          'Enforced release channels: %s.', self.args.enforced_release_channels)
    if self.args.gooftool_waive_list:
      command += ' --waive_list ' + ' '.join(self.args.gooftool_waive_list)
    if self.args.gooftool_skip_list:
      command += ' --skip_list ' + ' '.join(self.args.gooftool_skip_list)
    command += ' --phase "%s"' % phase.GetPhase()

    if not self.args.inform_shopfloor_after_wipe and shopfloor.is_enabled():
      shopfloor.finalize()  # notify shopfloor
    self._FinalizeWipeInPlace(command)

  def _FinalizeWipeInPlace(self, command):
    if self.dut.link.IsLocal():
      self._CallGoofTool(command)
      # Wipe-in-place will terminate all processes that are using stateful
      # partition, this test should be killed at here.
      time.sleep(self.FINALIZE_TIMEOUT)
      raise factory.FactoryTestFailure('DUT Failed to finalize in %d seconds' %
                                       self.FINALIZE_TIMEOUT)
    elif isinstance(self.dut.link, ssh.SSHLink):
      # For remote SSH DUT, we ask DUT to send wipe log back.
      return self._FinalizeRemoteSSHDUT(command)
    else:
      # For other remote links, we only checks if it has lost connection in
      # @self.FINALIZE_TIMEOUT seconds
      self._CallGoofTool(command)
      try:
        sync_utils.WaitFor(lambda: not self.dut.IsReady(),
                           self.FINALIZE_TIMEOUT,
                           poll_interval=1)
      except type_utils.TimeoutError:
        raise factory.FactoryTestFailure(
            'Remote DUT failed to finalize in %d seconds' %
            self.FINALIZE_TIMEOUT)
      self.ui.Pass()

  def _FinalizeRemoteSSHDUT(self, command):
    # generate a random token, so the response is different for every DUT.
    token = "{:016x}".format(random.getrandbits(64))

    dut_finished = threading.Event()
    self.dut_response = None

    def _Callback(handler):
      """Receive and verify DUT message.

      Args:
        :type handler: SocketServer.StreamRequestHandler
      """
      try:
        dut_response = json.loads(handler.rfile.readline())
        if dut_response['token'] == token:
          self.dut_response = dut_response
          dut_finished.set()
        # otherwise, the reponse is invalid, just ignore it
      except Exception:
        pass

    # Start response listener
    self.response_listener = net_utils.CallbackSocketServer(_Callback)
    server_thread = threading.Thread(
        target=self.response_listener.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # If station IP is not given, we assume that this station is the first host
    # in the subnet, and number of prefix bits in this subnet is 24.
    station_ip = (self.args.station_ip or
                  net_utils.CIDR(str(self.dut.link.host), 24).SelectIP(1))
    command += ' --station_ip "%s"' % station_ip
    command += ' --station_port %d' % self.response_listener.server_address[1]
    command += ' --wipe_finish_token "%s"' % token

    if not self._CallGoofTool(command):
      raise factory.FactoryTestFailure('finalize command failed')

    factory.console.info('wait DUT to finish wiping')

    if not dut_finished.wait(self.FINALIZE_TIMEOUT):
      raise factory.FactoryTestFailure(
          'Remote DUT not response in %d seconds' % self.FINALIZE_TIMEOUT)

    # save log files in test data directory
    output_dir = os.path.join(paths.DATA_TESTS_DIR,
                              factory.get_current_test_path())
    with open(os.path.join(output_dir, 'wipe_in_tmpfs.log'), 'w') as f:
      f.write(self.dut_response.get('wipe_in_tmpfs_log', ''))
    with open(os.path.join(output_dir, 'wipe_init.log'), 'w') as f:
      f.write(self.dut_response.get('wipe_init_log', ''))

    self.assertTrue(self.dut_response['success'])
    self.ui.Pass()
