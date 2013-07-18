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
from cros.factory.test.args import Arg

_CSS = """
#state {
  font-size: 200%;
}
.sync-detail {
  font-size: 40%;
  width: 75%;
  margin-left: 12.5%;
  padding-top: 2em;
  text-align: left;
}
"""

class SyncShopfloor(unittest.TestCase):
  ARGS = [
      Arg('first_retry_secs', int,
          'Time to wait after the first attempt; this will increase '
          'exponentially up to retry_secs.  This is useful because '
          'sometimes the network may not be available by the time the '
          'tests starts, but a full 10-second wait is unnecessary.',
          1),
      Arg('retry_secs', int, 'Maximum time to wait between retries', 10),
      Arg('timeout_secs', int, 'Timeout for XML/RPC operations', 10),
      Arg('update_without_prompt', bool, 'Update without prompting when an '
          'update is available', default=False, optional=True),
      Arg('sync_event_logs', bool, 'Sync event logs to shopfloor',
          default=True)
      ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    ui.AppendCSS(_CSS)

    def target():
      retry_secs = self.args.first_retry_secs

      while True:
        template.SetState(test_ui.MakeLabel(
            'Contacting shopfloor server...',
            '正在与shopfloor server连线...'))

        try:
          goofy = factory.get_state_instance()
          if self.args.sync_event_logs:
            goofy.FlushEventLogs()
          goofy.SyncTimeWithShopfloorServer()
          dummy_md5sum, needs_update = updater.CheckForUpdate(
              self.args.timeout_secs)
          if not needs_update:
            # No update necessary; pass.
            ui.Pass()
            return

          # Update necessary.
          if self.args.update_without_prompt:
            ui.RunJS('window.test.updateFactory()')
            return
          else:
            # Display message and require update.
            template.SetState(test_ui.MakeLabel(
                'A software update is available. '
                'Press SPACE to update.',

                u'有可用的更新。'
                u'安空白键更新。'))

            # Note that updateFactory() will kill this test.
            ui.BindKeyJS(' ', 'window.test.updateFactory()')
            return
        except:  # pylint: disable=W0702
          exception_string = utils.FormatExceptionOnly()
          # Log only the exception string, not the entire exception,
          # since this may happen repeatedly.
          logging.error('Unable to sync with shopfloor server: %s',
                        exception_string)

        template.SetState(
            test_ui.MakeLabel(
                ('Unable to contact shopfloor server. '
                 'Will try again in '),
                '无法连线到 shopfloor server。') +
            ('<span id="retry">%d</span>' % retry_secs) +
            test_ui.MakeLabel(
                ' seconds.',
                '秒后自动重试。') +
            '<div class=sync-detail>' +
            test_ui.Escape(exception_string) + '</div>')

        for i in xrange(retry_secs):
          time.sleep(1)
          ui.SetHTML(str(retry_secs - i - 1), id='retry')

        retry_secs = min(2 * retry_secs, self.args.retry_secs)

    utils.StartDaemonThread(target=target)
    ui.Run()
