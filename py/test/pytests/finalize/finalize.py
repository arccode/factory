# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The finalize test is the last step before DUT switching to release image.

The test checks if all tests are passed, and checks the hardware
write-protection, charge percentage. Then it invoke gooftool finalize with
specified arguments to switch the machine to release image.
"""


import logging
import os
import re
import threading
import time
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.event_log import Log
from cros.factory.gooftool import Gooftool
from cros.factory.system import SystemInfo
from cros.factory.test import factory
from cros.factory.test import gooftools
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel


MSG_CHECKING = MakeLabel("Checking system status for finalization...",
                         "正在检查系统是否已可执行最终程序...")
MSG_NOT_READY = MakeLabel("System is not ready.<br>"
                        "Please fix RED tasks and then press SPACE.",
                        "系统尚未就绪。<br>"
                        "请修正红色项目后按空白键重新检查。")
MSG_NOT_READY_POLLING = MakeLabel("System is NOT ready. Please fix RED tasks.",
                                  "系统尚未就绪。请修正红色项目。")
MSG_FORCE = MakeLabel("Press “f” to force starting finalization procedure.",
                      "按下 「f」 键以强迫开始最终程序。")
MSG_READY = MakeLabel("System is READY. Press SPACE to start FINALIZATION.",
                      "系统已準备就绪。 请按空白键开始最终程序!")
MSG_FINALIZING = MakeLabel(
    "Finalizing, please wait.<br>"
    "Do not restart the device or terminate this test,<br>"
    "or the device may become unusable.",
    "正在开始最终程序，请稍等.<br>"
    "不要重启机器或停止测试，<br>"
    "不然机器将无法开机。")

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
          'e.g.: [(r"^FATP\.FooBar$", r"Timeout"), (r"Diagnostic\..*")] will '
          'waive FATP.FooBar test if error message starts with Timeout. It '
          'will also waive all Diagnostic.* tests, either UNTESTED or FAILED. '
          'Error messages may be multiline (e.g., stack traces) so this is a '
          'multiline match.  This is a Python re.match operation, so it will '
          'match from the beginning of the error string.',
          default=[]),
      Arg('hwid_version', int,
          'Version of HWID library to use in gooftool.', default=3,
          optional=True),
      Arg('enable_shopfloor', bool,
          'Perform shopfloor operations: update HWID data and flush event '
          'logs.', default=True),
      Arg('sync_event_logs', bool, 'Sync event logs to shopfloor',
          default=True),
      Arg('rma_mode', bool,
          'Enable rma_mode, do not check for deprecated components.',
          default=False, optional=True),
      ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.force = False
    self.go_cond = threading.Condition()
    self.test_states_path = os.path.join(factory.get_log_root(),
                                         'test_states')
    self.gooftool = Gooftool(hwid_version=self.args.hwid_version)

    # Set of waived tests.
    self.waived_tests = set()

    # Normalize 0 to None (since various things, e.g.,
    # Condition.wait(timeout), treat 0 and None differently.
    if self.args.polling_seconds == 0:
      self.args.polling_seconds = None

  def runTest(self):
    # Check for HWID bundle update from shopfloor.
    if self.args.enable_shopfloor:
      shopfloor.update_local_hwid_data()

    # Check waived_tests argument.
    test_list = self.test_info.ReadTestList()

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

    test_states = test_list.as_dict(
      factory.get_state_instance().get_test_states())

    with open(self.test_states_path, 'w') as f:
      yaml.dump(test_states, f)

    Log('test_states', test_states=test_states)

    def Go(force=False):
      with self.go_cond:
        if self.ForcePermissions():
          self.force = force
        self.go_cond.notify()
    self.ui.BindKey(' ', lambda _: Go(False))
    self.ui.BindKey('F', lambda _: Go(True))

    thread = threading.Thread(target=self.Run)
    thread.start()
    self.ui.Run()

  def Run(self):
    try:
      self.LogImageVersion()
      self.RunPreflight()
      self.template.SetState(MSG_FINALIZING)
      self.DoFinalize()
      self.ui.Fail('Should never be reached')
    except Exception, e:  # pylint: disable=W0703
      self.ui.Fail('Exception during finalization: %s' % e)

  def LogImageVersion(self):
    system_info = SystemInfo()
    release_image_version = system_info.release_image_version
    factory_image_version = system_info.factory_image_version
    if release_image_version:
      logging.info('release image version: %s', release_image_version)
    else:
      self.ui.Fail('Can not determine release image version')
    if factory_image_version:
      logging.info('factory image version: %s', factory_image_version)
    else:
      self.ui.Fail('Can not determine factory image version')
    Log('finalize_image_version',
        factory_image_version=factory_image_version,
        release_image_version=release_image_version)

  def RunPreflight(self):
    power = system.GetBoard().power
    def CheckRequiredTests():
      '''Returns True if all tests (except waived tests) have passed.'''
      test_list = self.test_info.ReadTestList()
      state_map = factory.get_state_instance().get_test_states()

      self.waived_tests = set()

      for k, v in state_map.iteritems():
        test = test_list.lookup_path(k)
        if not test:
          # Test has been removed (e.g., by updater).
          continue

        if test.subtests:
          # There are subtests.  Don't check the parent itself (only check
          # the children).
          continue

        if v.status == factory.TestState.UNTESTED:
          # See if it's been waived. The regular expression of error messages
          # must be empty string.
          waived = False
          for regex_path, regex_error_msg in self.args.waive_tests:
            if regex_path.match(k) and not regex_error_msg.pattern:
              self.waived_tests.add(k)
              waived = True
              logging.info('Waived UNTESTED test %r', k)
              break

          if not waived:
            # It has not been waived.
            return False

        if v.status == factory.TestState.FAILED:
          # See if it's been waived.
          waived = False
          for regex_path, regex_error_msg in self.args.waive_tests:
            if regex_path.match(k) and regex_error_msg.match(v.error_msg):
              self.waived_tests.add(k)
              waived = True
              logging.info('Waived FAILED test %r', k)
              break

          if not waived:
            # It has not been waived.
            return False

      return True

    items = [(CheckRequiredTests,
              MakeLabel("Verify all tests passed",
                        "确认测试项目都已成功了")),
             (lambda: (
                self.gooftool.CheckDevSwitchForDisabling() in (True, False)),
              MakeLabel("Turn off Developer Switch",
                        "停用开发者开关(DevSwitch)"))]
    if self.args.min_charge_pct:
      items.append((lambda: (power.CheckBatteryPresent() and
                             power.GetChargePct() >= self.args.min_charge_pct),
                    MakeLabel("Charge battery to %d%%" %
                              self.args.min_charge_pct,
                              "充电到%d%%" %
                              self.args.min_charge_pct)))
    if self.args.write_protection:
      items += [(lambda: self.gooftool.VerifyWPSwitch() == None,
                 MakeLabel("Enable write protection pin",
                           "确认硬体写入保护已开启"))]

    self.template.SetState(
        '<table style="margin: auto; font-size: 150%"><tr><td>' +
        '<div id="finalize-state">%s</div>' % MSG_CHECKING +
        '<table style="margin: auto"><tr><td>' +
        '<ul id="finalize-list" style="margin-top: 1em">' +
        ''.join(['<li id="finalize-%d">%s' % (i, item[1])
                 for i, item in enumerate(items)]),
        '</ul>'
        '</td></tr></table>'
        '</td></tr></table>')

    def UpdateState():
      '''Polls and updates the states of all checklist items.

      Returns:
        True if all have passed.
      '''
      all_passed = True
      js = []
      for i, item in enumerate(items):
        try:
          passed = item[0]()
        except:  # pylint: disable=W0702
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
          '(will continue in %d seconds)' % (message, i))
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
                                    shopfloor.get_serial_number())
    logging.info('Using upload method %s', method)

    return method

  def DoFinalize(self):
    upload_method = self.NormalizeUploadMethod(self.args.upload_method)

    command = 'gooftool -v 4 finalize -i %d' % self.args.hwid_version
    if self.waived_tests:
      self.Warn('TESTS WERE WAIVED: %s.' % sorted(list(self.waived_tests)))
    Log('waived_tests', waived_tests=sorted(list(self.waived_tests)))

    if self.args.enable_shopfloor and self.args.sync_event_logs:
      factory.get_state_instance().FlushEventLogs()

    if not self.args.write_protection:
      self.Warn('WRITE PROTECTION IS DISABLED.')
      command += ' --no_write_protect'
    if not self.args.secure_wipe:
      command += ' --fast'
    command += ' --upload_method "%s"' % upload_method
    command += ' --add_file "%s"' % self.test_states_path
    if self.args.rma_mode:
      command += ' --rma_mode'
      logging.info('Using RMA mode. Accept deprecated components')

    gooftools.run(command)

    if shopfloor.is_enabled():
      shopfloor.finalize()

    # TODO(hungte): Use Reboot in test list to replace this, or add a
    # key-press check in developer mode.
    os.system("sync; sync; sync; shutdown -r now")
    time.sleep(60)
    self.ui.Fail('Unable to shutdown')
