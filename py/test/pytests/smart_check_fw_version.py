# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Checks firmware version on disk using smartctl.

If the test fails, then the test displays an error message and hangs forever.
"""


import logging
import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class SMARTCheckFWVersionTest(unittest.TestCase):
  ARGS = [
      Arg('regexp', str, 'Expected firmware revision (regexp)'),
      Arg('device', str, 'Device path to check', default='sda'),
  ]

  def runTest(self):
    smartctl = process_utils.Spawn(
        ['smartctl', '-a', '/dev/%s' % self.args.device],
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
    template.SetTitle(
        i18n_test_ui.MakeI18nLabel('SSD Firmware Version Incorrect'))
    template.SetState(
        '<div class=test-status-failed style="font-size: 150%">' +
        i18n_test_ui.MakeI18nLabel(
            'The SSD firmware version ({fw_version}) is incorrect. '
            '<br>Please run the SSD firmware update tool.',
            fw_version=test_ui.Escape(fw_version)) + '</div>')
    ui.Run()  # Forever
