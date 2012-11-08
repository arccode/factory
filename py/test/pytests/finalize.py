# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import threading
import time
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.system.power import Power
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
MSG_FINALIZING = MakeLabel("Finalizing, please wait...",
                           "正在开始最终程序，請稍等...")


class Finalize(unittest.TestCase):
  ARGS = [
      Arg('write_protection', bool,
          'Check write protection.', default=True),
      Arg('polling_seconds', (int, type(None)),
          'Interval between updating results (None to disable polling).',
          default=5),
      Arg('allow_force_finalize', bool,
          'Allow the user to force finalization (even in operator mode).',
          default=True),
      Arg('min_charge_pct', int,
          'Minimum battery charge percentage allowed (None to disable '
          'checking charge level)',
          optional=True),
      Arg('secure_wipe', bool,
          'Wipe the stateful partition securely (False for a fast wipe).',
          default=True),
      Arg('upload_method', str,
          'Upload method for "gooftool finalize"',
          optional=True)
      ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.force = False
    self.go_cond = threading.Condition()
    self.test_states_path = os.path.join(factory.get_log_root(),
                                         'test_states')

    # Normalize 0 to None (since various things, e.g.,
    # Condition.wait(timeout), treat 0 and None differently.
    if self.args.polling_seconds == 0:
      self.args.polling_seconds = None

  def runTest(self):
    test_list = self.test_info.ReadTestList()
    test_states = test_list.as_dict(
      factory.get_state_instance().get_test_states())

    with open(self.test_states_path, 'w') as f:
      yaml.dump(test_states, f)

    event_log.EventLog.ForAutoTest().Log('test_states',
                                         test_states=test_states)

    def Go(force=False):
      with self.go_cond:
        if (self.args.allow_force_finalize or
            self.ui.InEngineeringMode()):
          self.force = force
        self.go_cond.notify()
    self.ui.BindKey(' ', lambda _: Go(False))
    self.ui.BindKey('F', lambda _: Go(True))

    thread = threading.Thread(target=self.Run)
    thread.start()
    self.ui.Run()

  def Run(self):
    try:
      self.RunPreflight()
      self.template.SetState(MSG_FINALIZING)
      self.DoFinalize()
      self.ui.Fail('Should never be reached')
    except Exception, e:  # pylint: disable=W0703
      self.ui.Fail('Exception during finalization: %s' % e)

  def RunPreflight(self):
    power = Power()
    def CheckRequiredTests():
      '''Returns True if all tests have passed.'''
      state_map = factory.get_state_instance().get_test_states()
      return not any(x.status in [factory.TestState.FAILED,
                                  factory.TestState.UNTESTED]
                     for x in state_map.values())

    items = [(CheckRequiredTests,
              MakeLabel("Verify all tests passed",
                        "确认测试项目都已成功了")),
             (lambda: gooftools.run('gooftool verify_switch_dev'),
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
      items += [(lambda: gooftools.run('gooftool verify_switch_wp'),
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
        if self.args.allow_force_finalize:
          msg += '<div>' + MSG_FORCE + '</div>'
        else:
          msg += '<div class=test-engineering-mode-only>' + MSG_FORCE + '</div>'
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

    command = 'gooftool -v 4 -l %s finalize' % factory.CONSOLE_LOG_PATH
    if not self.args.write_protection:
      self.Warn('WRITE PROTECTION IS DISABLED.')
      command += ' --no_write_protect'
    if not self.args.secure_wipe:
      command += ' --fast'
    command += ' --upload_method "%s"' % upload_method
    command += ' --add_file "%s"' % self.test_states_path

    gooftools.run(command)

    # TODO(hungte): Use Reboot in test list to replace this, or add a
    # key-press check in developer mode.
    os.system("sync; sync; sync; shutdown -r now")
    time.sleep(60)
    self.ui.Fail('Unable to shutdown')
