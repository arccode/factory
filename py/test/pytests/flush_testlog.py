# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
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


class FlushTestlog(unittest.TestCase):
  ARGS = [
      Arg('first_retry_secs', int,
          'Time to wait after the first attempt; this will increase '
          'exponentially up to retry_secs.  This is useful because '
          'sometimes the network may not be available by the time the '
          'tests starts, but a full 10-second wait is unnecessary.',
          1),
      Arg('retry_secs', int, 'Maximum time to wait between retries', 10),
      Arg('timeout_secs', int, 'Timeout for XML/RPC operations', 10),
  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    goofy = factory.get_state_instance()
    ui.AppendCSS(_CSS)

    def target():
      retry_secs = self.args.first_retry_secs

      while True:
        try:
          template.SetState(
              i18n_test_ui.MakeI18nLabel(
                  'Attempting to flush logs upstream...'))
          msg = goofy.FlushTestlog(timeout=self.args.timeout_secs)
          factory.console.info('Logs flushed successfully: %s', msg)
          ui.Pass()
          return
        except:  # pylint: disable=W0702
          exception_string = debug_utils.FormatExceptionOnly()
          # Log only the exception string, not the entire exception,
          # since this may happen repeatedly.
          logging.error('Unable to flush logs: %s', exception_string)

        msg = lambda secs: i18n_test_ui.MakeI18nLabel(
            'Unable to flush logs. Will try again in {secs} seconds.',
            secs=secs)
        template.SetState('<span id="retry">' + msg(retry_secs) + '</span>' +
                          '<div class=sync-detail>' +
                          test_ui.Escape(exception_string) + '</div>')

        for i in xrange(retry_secs):
          time.sleep(1)
          ui.SetHTML(msg(retry_secs - i - 1), id='retry')

        retry_secs = min(2 * retry_secs, self.args.retry_secs)

    process_utils.StartDaemonThread(target=target)
    ui.Run()
