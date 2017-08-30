# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Connect to factory server to find software updates and upload logs.

Description
-----------
This test will create connections from DUT to Chrome OS factory server and
invoke remote procedure calls for syncing data and programs.

This test will sync following items:

1. If ``sync_time`` is enabled (default True), sync system time from server.
2. If ``sync_event_logs`` is enabled (default True), sync the ``event_log`` YAML
   event logs to factory server.
3. If ``flush_testlog`` is enabled (default False), flush TestLog to factory
   server (which should have Instalog node running).
4. If ``upload_report`` is enabled (default False), upload a ``Gooftool`` style
   report collecting system information and manufacturing logs to server.
5. If ``update_toolkit`` is enabled (default True), compare the factory software
   (toolkit) installed on DUT with the active version on server, and update
   if needed.

Additionally, if argument ``server_url`` is specified, this test will update the
stored 'default factory server URL' so all following tests connecting to factory
server via ``server_proxy.GetServerProxy()`` will use the new URL.

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

To sync time and logs, and then upload a report::

  OperatorTest(pytest_name='sync_factory_server',
               dargs={'upload_report': True})

To override default factory server URL for all tests executed after this::

  OperatorTest(pytest_name='sync_factory_server',
               dargs={'server_url': 'http://192.168.3.11:8080'})

To implement "station specific factory server" in JSON test lists, extend
``SyncFactoryServer`` from ``generic_common.test_list.json`` as::

  { "inherit": "SyncFactoryServer",
    "args": {
      "server_url": "eval! locals.factory_server_url"
    }
  }

And then in each station (or stage), override URL in locals::

  {"SMT": {"locals": {"factory_server_url": "http://192.168.3.11:8080" }}},
  {"FAT": {"locals": {"factory_server_url": "http://10.3.0.11:8080" }}},
  {"RunIn": {"locals": {"factory_server_url": "http://10.1.2.10:7000" }}},
  {"FFT": {"locals": {"factory_server_url": "http://10.3.0.11:8080" }}},
  {"GRT": {"locals": {"factory_server_url": "http://172.30.1.2:8081" }}},
"""

import logging
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool import commands
from cros.factory.goofy import updater
from cros.factory.test import device_data
from cros.factory.test import factory
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import server_proxy
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import time_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils

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

.warning_label {
  font-weight: bold;
  color: red;
}

.warning_message {
  color: #ca0;
}

#text_input_url {
  width: 18em;
  font-family: monospace;
  font-size: 1em;
  margin: 10px;
}
"""


ID_TEXT_INPUT_URL = 'text_input_url'
ID_BUTTON_EDIT_URL = 'button_edit_url'

EVENT_SET_URL = 'event_set_url'
EVENT_CANCEL_SET_URL = 'event_cancel_set_url'
EVENT_DO_SET_URL = 'event_do_set_url'

# TODO(hungte) Add message when we can't connect to factory server.
_LABEL_NO_FACTORY_SERVER_URL = i18n_test_ui.MakeI18nLabelWithClass(
    'No factor server URL configured.', 'warning_label')

_MSG_DEBUG_HINT = i18n_test_ui.MakeI18nLabelWithClass(
    'For debugging or development, '
    'enter engineering mode to start individual tests.', 'warning_message')


class Report(object):
  """A structure for reports uploaded to factory server."""

  def __init__(self, serial_number, blob, station):
    self.serial_number = serial_number
    self.blob = blob
    self.station = station


class SyncFactoryServer(unittest.TestCase):
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
          default=True),
      Arg('update_without_prompt', bool, 'Update without prompting when an '
          'update is available.', default=False),
      Arg('sync_time', bool, 'Sync system time from factory server.',
          default=True),
      Arg('sync_event_logs', bool, 'Sync event logs to factory server.',
          default=True),
      Arg('flush_testlog', bool, 'Flush test logs to factory server.',
          # TODO(hungte) Change flush_testlog to default True when Umpire is
          # officially deployed.
          default=False),
      Arg('upload_report', bool, 'Upload a factory report to factory server.',
          default=False),
      Arg('report_stage', str, 'Stage of report to upload.', default=None),
      Arg('report_serial_number_name', str,
          'Name of serial number to use for report file name to use.',
          default=None),
      Arg('server_url', str, 'Set and keep new factory server URL.',
          default=None),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.ui_template = ui_templates.TwoSections(self.ui)
    self.server = None
    self.do_setup_url = False
    self.allow_edit_url = True
    self.event_url_set = threading.Event()
    self.goofy = state.get_instance()
    self.report = Report(None, None, self.args.report_stage)

  def runTest(self):
    self.ui.AppendCSS(_CSS)
    self.ui_template.DrawProgressBar()
    self.ui.RunInBackground(self._runTest)
    self.ui.Run()

  @staticmethod
  def CreateButton(node_id, message, on_click):
    return ('<button type="button" id="%s" onClick=%r>%s</button>' %
            (node_id, on_click, message))

  def CreateChangeURLButton(self):
    return self.CreateButton(
        ID_BUTTON_EDIT_URL, i18n_test_ui.MakeI18nLabel('Change URL'),
        'this.disabled = true; window.test.sendTestEvent("%s");' %
        EVENT_DO_SET_URL)

  def OnButtonSetClicked(self, event):
    self.ChangeServerURL(event.data)
    self.do_setup_url = False
    self.event_url_set.set()

  def OnButtonCancelClicked(self, event):
    del event  # Unused.
    self.do_setup_url = False
    self.event_url_set.set()

  def OnButtonEditClicked(self, event):
    del event  # Unused.
    self.do_setup_url = True
    self.ui.SetHTML(
        i18n_test_ui.MakeI18nLabel('Please wait few seconds to edit...'),
        id=ID_BUTTON_EDIT_URL)

  def EditServerURL(self):
    current_url = server_proxy.GetServerURL() or ''
    if current_url:
      prompt = ''
    else:
      prompt = '<br/>'.join([
          _LABEL_NO_FACTORY_SERVER_URL,
          _MSG_DEBUG_HINT,
          ''])

    self.ui_template.SetState(
        prompt + i18n_test_ui.MakeI18nLabel('Change server URL: ') + '<br/>' +
        '<input type="text" id="%s" value="%s"/><br/>' %
        (ID_TEXT_INPUT_URL, current_url) +
        self.CreateButton(
            'btnSet', i18n_test_ui.MakeI18nLabel('Set'),
            'window.test.sendTestEvent("%s", '
            'document.getElementById("%s").value)' %
            (EVENT_SET_URL, ID_TEXT_INPUT_URL)) +
        self.CreateButton(
            'btnCancel', i18n_test_ui.MakeI18nLabel('Cancel'),
            'window.test.sendTestEvent("%s")' % EVENT_CANCEL_SET_URL))

  def Ping(self):
    if self.do_setup_url:
      self.event_url_set.clear()
      self.EditServerURL()
      self.event_url_set.wait()

    self.ui_template.SetState(
        i18n_test_ui.MakeI18nLabel('Trying to reach server...') +
        '<br/><br/>' + self.CreateChangeURLButton())
    self.server = server_proxy.GetServerProxy(timeout=self.args.timeout_secs)

    if self.do_setup_url:
      raise Exception('Edit URL clicked.')

    self.ui_template.SetState(
        i18n_test_ui.MakeI18nLabel('Trying to check server protocol...') +
        '<br/><br/>' + self.CreateChangeURLButton())
    self.server.Ping()
    self.allow_edit_url = False

  def ChangeServerURL(self, new_server_url):
    server_url = server_proxy.GetServerURL() or ''

    if new_server_url and new_server_url != server_url:
      server_proxy.SetServerURL(new_server_url.rstrip('/'))
      # Read again because server_proxy module may normalize it.
      new_server_url = server_proxy.GetServerURL()
      factory.console.info(
          'Factory server URL has been changed from [%s] to [%s].',
          server_url, new_server_url)
      server_url = new_server_url

    self.ui_template.SetInstruction(
        i18n_test_ui.MakeI18nLabel('Server URL: ') + server_url)
    if not server_url:
      self.do_setup_url = True

  def FlushTestlog(self):
    # TODO(hungte) goofy.FlushTestlog should reload factory_server_url.
    self.goofy.FlushTestlog(timeout=self.args.timeout_secs)

  def CreateReport(self):
    self.ui_template.SetState(i18n_test_ui.MakeI18nLabel(
        'Collecting report data...'))
    self.report.blob = commands.CreateReportArchiveBlob()
    self.ui_template.SetState(i18n_test_ui.MakeI18nLabel(
        'Getting serial number...'))
    self.report.serial_number = device_data.GetSerialNumber(
        self.args.report_serial_number_name or
        device_data.NAME_SERIAL_NUMBER)

  def UploadReport(self):
    self.server.UploadReport(
        self.report.serial_number, self.report.blob, self.report.station)

  def UpdateToolkit(self):
    unused_toolkit_version, has_update = updater.CheckForUpdate(
        self.args.timeout_secs)
    if not has_update:
      return

    # Update necessary. Note that updateFactory() will kill this test.
    if self.args.update_without_prompt:
      self.ui.RunJS('window.test.updateFactory()')
    else:
      # Display message and require update.
      self.ui_template.SetState(i18n_test_ui.MakeI18nLabel(
          'A software update is available. Press SPACE to update.'))
      self.ui.BindKeyJS(test_ui.SPACE_KEY, 'window.test.updateFactory()')

    # Let this test sleep forever, and wait for either the SPACE event, or the
    # factory update to complete. Note that we want the test to neither pass or
    # fail, so we won't be accidentally running other tests when the
    # updateFactory is running.
    while True:
      time.sleep(1000)

  def _runTest(self):
    self.ui_template.SetInstruction(i18n_test_ui.MakeI18nLabel('Preparing...'))
    retry_secs = self.args.first_retry_secs

    self.ui.AddEventHandler(EVENT_SET_URL, self.OnButtonSetClicked)
    self.ui.AddEventHandler(EVENT_CANCEL_SET_URL, self.OnButtonCancelClicked)
    self.ui.AddEventHandler(EVENT_DO_SET_URL, self.OnButtonEditClicked)

    # Setup tasks to perform.
    tasks = [(_('Ping'), self.Ping)]

    if self.args.sync_time:
      tasks += [(_('Sync time'), time_utils.SyncTimeWithFactoryServer)]

    if self.args.sync_event_logs:
      tasks += [(_('Flush Event Logs'), self.goofy.FlushEventLogs)]

    if self.args.flush_testlog:
      tasks += [(_('Flush Test Log'), self.FlushTestlog)]

    if self.args.upload_report:
      tasks += [(_('Create Report'), self.CreateReport)]
      tasks += [(_('Upload report'), self.UploadReport)]

    if self.args.update_toolkit:
      tasks += [(_('Update Toolkit'), self.UpdateToolkit)]
    else:
      factory.console.info('Toolkit update is disabled.')

    # Setup new server URL
    self.ChangeServerURL(self.args.server_url)

    for i, (label, task) in enumerate(tasks):
      progress = int(i * 100.0 / len(tasks))
      self.ui_template.SetProgressBarValue(progress)
      while True:
        try:
          self.ui_template.SetState(i18n_test_ui.MakeI18nLabel(
              'Running task: {label}', label=label) + '<br>')
          task()
          self.ui_template.SetState(
              '<span style="color: green">' +
              i18n_test_ui.MakeI18nLabel(
                  'Server Task Finished: {label}', label=label) +
              '</span>')
          time.sleep(0.5)
          break
        except server_proxy.Fault as f:
          exception_string = f.faultString
          logging.error('Server fault with message: %s', f.faultString)
        except Exception:
          exception_string = debug_utils.FormatExceptionOnly()
          # Log only the exception string, not the entire exception,
          # since this may happen repeatedly.
          logging.error('Unable to sync with server: %s', exception_string)

        msg = lambda time_left, label_: i18n_test_ui.MakeI18nLabel(
            'Task <b>{label}</b> failed, retry in {time_left} seconds...',
            time_left=time_left, label=label_)
        edit_url_button = (('<p>' + self.CreateChangeURLButton() + '</p>')
                           if self.allow_edit_url else '')
        self.ui_template.SetState(
            '<span id="retry">' + msg(retry_secs, label) + '</span>'
            + edit_url_button
            + '<p><textarea rows=25 cols=90 readonly class=sync-detail>'
            + test_ui.Escape(exception_string, False) + '</textarea>')

        for i in xrange(retry_secs):
          time.sleep(1)
          self.ui.SetHTML(msg(retry_secs - i - 1, label), id='retry')
        retry_secs = min(2 * retry_secs, self.args.retry_secs)
