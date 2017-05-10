#!/usr/bin/python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import updater
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import process_utils

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
      Arg('disable_update', bool, 'Whether to check factory update',
          default=False, optional=True),
      Arg('update_without_prompt', bool, 'Update without prompting when an '
          'update is available', default=False, optional=True),
      Arg('sync_event_logs', bool, 'Sync event logs to shopfloor',
          default=True)
  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    ui.AppendCSS(_CSS)
    if self.args.disable_update:
      factory.console.info('Update is disabled.')

    def target():
      retry_secs = self.args.first_retry_secs

      def needs_update():
        unused_md5sum, has_update = updater.CheckForUpdate(
            self.args.timeout_secs)
        return has_update

      while True:
        template.SetState(
            i18n_test_ui.MakeI18nLabel('Contacting shopfloor server...'))
        shopfloor_url = shopfloor.get_server_url()
        if shopfloor_url:
          template.SetState('<br>' + shopfloor_url, append=True)

        try:
          goofy = state.get_instance()
          if self.args.sync_event_logs:
            goofy.FlushEventLogs()
          goofy.SyncTimeWithShopfloorServer()
          if self.args.disable_update or not needs_update():
            # No update necessary; pass.
            ui.Pass()
            return

          # Update necessary.
          if self.args.update_without_prompt:
            ui.RunJS('window.test.updateFactory()')
            return
          else:
            # Display message and require update.
            template.SetState(
                i18n_test_ui.MakeI18nLabel('A software update is available. '
                                           'Press SPACE to update.'))

            # Note that updateFactory() will kill this test.
            ui.BindKeyJS(test_ui.SPACE_KEY, 'window.test.updateFactory()')
            return
        except:  # pylint: disable=bare-except
          exception_string = debug_utils.FormatExceptionOnly()
          # Log only the exception string, not the entire exception,
          # since this may happen repeatedly.
          logging.error('Unable to sync with shopfloor server: %s',
                        exception_string)

        msg = lambda time_left: i18n_test_ui.MakeI18nLabel(
            'Unable to contact shopfloor server.'
            ' Will try again in {time_left} seconds.', time_left=time_left)
        template.SetState(
            '<span id="retry">' + msg(retry_secs) + '</span>'
            + '<div class=sync-detail>'
            + test_ui.Escape(exception_string) + '</div>')

        for i in xrange(retry_secs):
          time.sleep(1)
          ui.SetHTML(msg(retry_secs - i - 1), id='retry')

        retry_secs = min(2 * retry_secs, self.args.retry_secs)

    process_utils.StartDaemonThread(target=target)
    ui.Run()
