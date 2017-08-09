# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Connect to factory server to find software updates and upload logs.

Description
-----------
This test will create connections from DUT to Chrome OS factory server and
invoke remote procedure calls for syncing data and programs.

This test will sync following items:

1. If `sync_time` is enabled (default True), sync system time with server time.
2. If `sync_event_logs` is enabled (default True), sync the `event_log` YAML
   event logs to factory server.
3. If `upload_report` is enabled (default False), upload a Gooftool style report
   collecting various system information and manufacturing logs to server.
4. If `update_toolkit` is enabled (default True), compare the factory software
   (toolkit) installed on DUT with the active version on server, and update
   if needed.

Test Procedure
--------------
Basically no user interaction required unless a toolkit update is found.

- Make sure network is connected.
- Start the test and it will try to reach factory server and sync time and logs.
- If `update_toolkit` is True, compare installed toolkit with server's active
  version.
- If a new version is found, a message like 'A software update is available.'
  will be displayed on screen. Operator can follow the instruction (usually
  just press space) to start downloading and installing new software.

Dependency
----------
Nothing special.
This test uses only server components in Chrome OS Factory Software.

Examples
--------
To connect to default server and sync time, event logs, and update software::

  OperatorTest(pytest_name='sync_factory_server')

To only sync time and logs, and never update software (useful for stations)::

  OperatorTest(pytest_name='sync_factory_server',
               dargs={'update_toolkit': False})

To also upload a report::

  OperatorTest(pytest_name='sync_factory_server',
               dargs={'upload_report': True})
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import commands
from cros.factory.goofy import updater
from cros.factory.test import device_data
from cros.factory.test import factory
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import time_utils
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

class WaitForUpdate(Exception):
  pass


class SyncShopfloor(unittest.TestCase):
  ARGS = [
      Arg('first_retry_secs', int,
          'Time to wait after the first attempt; this will increase '
          'exponentially up to retry_secs.  This is useful because '
          'sometimes the network may not be available by the time the '
          'tests starts, but a full 10-second wait is unnecessary.',
          1),
      Arg('retry_secs', int, 'Maximum time to wait between retries.', 10),
      Arg('timeout_secs', int, 'Timeout for XML/RPC operations.', 10),
      Arg('update_toolkit', bool, 'Whether to check factory update.',
          default=True, optional=True),
      Arg('update_without_prompt', bool, 'Update without prompting when an '
          'update is available.', default=False, optional=True),
      Arg('sync_time', bool, 'Sync system time from factory server.',
          default=True),
      Arg('sync_event_logs', bool, 'Sync event logs to factory server.',
          default=True),
      Arg('upload_report', bool, 'Upload a factory report to factory server.',
          default=False),
      Arg('report_stage', str, 'Stage of report to upload.', default=None),
      Arg('report_serial_number_name', str,
          'Name of serial number to use for report file name to use.',
          default=None),
  ]

  def UpdateToolkit(self, force_update, timeout_secs, ui, template):
    unused_md5sum, has_update = updater.CheckForUpdate(timeout_secs)
    if not has_update:
      return

    # Update necessary.
    if force_update:
      ui.RunJS('window.test.updateFactory()')
    else:
      # Display message and require update.
      template.SetState(
          i18n_test_ui.MakeI18nLabel('A software update is available. '
                                     'Press SPACE to update.'))

      # Note that updateFactory() will kill this test.
      ui.BindKeyJS(test_ui.SPACE_KEY, 'window.test.updateFactory()')
    raise WaitForUpdate

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    ui.AppendCSS(_CSS)
    if not self.args.update_toolkit:
      factory.console.info('Update is disabled.')

    def target():
      retry_secs = self.args.first_retry_secs
      goofy = state.get_instance()
      server_url = shopfloor.get_server_url()
      server = shopfloor.get_instance()

      connect_label = i18n_test_ui.MakeI18nLabel(
          'Contacting factory server {server_url}...<br> Current Task: ',
          server_url=server_url or '')

      # Setup tasks to perform.
      tasks = []

      if self.args.sync_time:
        tasks += [(_('Sync time'), time_utils.SyncTimeWithShopfloorServer)]

      if self.args.sync_event_logs:
        tasks += [(_('Flush Event Logs'), goofy.FlushEventLogs)]

      if self.args.upload_report:
        blob = commands.CreateReportArchiveBlob()
        report_serial_number = device_data.GetSerialNumber(
            self.args.report_serial_number_name or
            device_data.NAME_SERIAL_NUMBER)
        tasks += [(_('Upload report'),
                   lambda: server.UploadReport(report_serial_number, blob, None,
                                               self.args.report_stage))]

      if self.args.update_toolkit:
        tasks += [(_('Update Toolkit'),
                   lambda: self.UpdateToolkit(self.args.update_without_prompt,
                                              self.args.timeout_secs, ui,
                                              template))]

      for label, task in tasks:
        while True:
          try:
            template.SetState(connect_label)
            template.SetState(i18n_test_ui.MakeI18nLabel(label), append=True)
            task()
            template.SetState(i18n_test_ui.MakeI18nLabel(
                '<span style="color: green">Server Task Finished: '
                '{label}</span>', label=label))
            time.sleep(0.5)
            break
          except WaitForUpdate:
            return
          except shopfloor.Fault as f:
            exception_string = f.faultString
            logging.error('Server fault with message: %s', f.faultString)
          except Exception:
            exception_string = debug_utils.FormatExceptionOnly()
            # Log only the exception string, not the entire exception,
            # since this may happen repeatedly.
            logging.error('Unable to sync with server: %s', exception_string)

          msg = lambda time_left, label_: i18n_test_ui.MakeI18nLabel(
              'Failed in task <b>{label}</b>.<br>'
              'Retry in {time_left} seconds...',
              time_left=time_left, label=label_)
          template.SetState(
              '<span id="retry">' + msg(retry_secs, label) + '</span>'
              + '<p><textarea rows=25 cols=90 readonly class=sync-detail>'
              + test_ui.Escape(exception_string, False) + '</textarea>')

          for i in xrange(retry_secs):
            time.sleep(1)
            ui.SetHTML(msg(retry_secs - i - 1, label), id='retry')
          retry_secs = min(2 * retry_secs, self.args.retry_secs)
      ui.Pass()

    process_utils.StartDaemonThread(target=target)
    ui.Run()
