# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''Checks firmware version on disk using smartctl.

If the test fails, then the test displays an error message and hangs forever.'''


import logging
import re
import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import Escape
from cros.factory.utils.process_utils import Spawn


class SMARTCheckFWVersionTest(unittest.TestCase):
  ARGS = [
    Arg('regexp', str, 'Expected firmware revision (regexp)'),
    Arg('device', str, 'Device path to check', default='sda'),
  ]

  def runTest(self):
    smartctl = Spawn(['smartctl', '-a', '/dev/%s' % self.args.device],
                     check_output=True, log=True).stdout_data
    logging.info('smartctl output:\n%s', smartctl)

    match = re.search('^Firmware Version: (.+)$', smartctl,
                      re.MULTILINE)
    self.assertTrue(match, 'Unable to parse smartctl output')

    fw_version = match.group(1)

    if re.match(self.args.regexp, fw_version):
      # Passed.
      logging.info('Firmware version is correct')
      return  # Pass the test

    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetTitle(test_ui.MakeLabel(
        'SSD Firmware Version Incorrect',
        'SSD 韧体版本不对'))
    template.SetState(
        '<div class=test-status-failed style="font-size: 150%">' +
        test_ui.MakeLabel(
            'The SSD firmware version (%s) is incorrect. '
            '<br>Please run the SSD firmware update tool.' % Escape(fw_version),

            'SSD 韧体版（%s）版本不对。'
            '<br>必须更新 SSD 韧体并重新安装工厂测试软件。' % Escape(fw_version)) +
        '</div>')
    ui.Run()  # Forever
