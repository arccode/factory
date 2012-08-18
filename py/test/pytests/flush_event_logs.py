#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import updater
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils


class FlushEventLogs(unittest.TestCase):
  def runTest(self):
    retry_secs = self.test_info.args.get('retry_secs', 10)
    timeout_secs = self.test_info.args.get('timeout_secs', 10)

    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    ui.AppendCSS('#state { text-align: left }')

    def target():
      while True:
        template.SetState(test_ui.MakeLabel(
            'Contacting shopfloor server...',
            '正在与shopfloor server连线...'))

        try:
          factory.get_state_instance().FlushEventLogs()
          dummy_md5sum, needs_update = updater.CheckForUpdate(timeout_secs)
          if not needs_update:
            # No update necessary; pass.
            ui.Pass()
            return

          # Update necessary.  Display message and require update.
          template.SetState(test_ui.MakeLabel(
              'A software update is available. '
              'Press SPACE to update.',

              u'有可用的更新。'
              u'安空白键更新。'))

          # Note that updateFactory() will kill this test.
          ui.BindKeyJS(' ', 'window.test.updateFactory()')
          return
        except:  # pylint: disable=W0702
          logging.exception('Unable to flush event logs')
          exception_string = utils.FormatExceptionOnly()

        template.SetState(
            test_ui.MakeLabel(
                ('Unable to contact shopfloor server. '
                 'Will try again in '),
                '无法连线到 shopfloor server。') +
            ('<span id="retry">%d</span>' % retry_secs) +
            test_ui.MakeLabel(
                ' seconds.',
                '秒后自动重试。') +
            '<br><br>' +
            test_ui.Escape(exception_string))

        for i in xrange(retry_secs):
          time.sleep(1)
          ui.SetHTML(str(retry_secs - i - 1), id='retry')

    utils.StartDaemonThread(target=target)
    ui.Run()
