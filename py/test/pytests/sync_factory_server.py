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
6. If ``upload_reg_codes`` is enabled (default False), upload the registration
   codes to server using ``UploadCSVEntry`` API, and have the data stored in
   ``registration_code_log.csv`` file on server. If the reg codes must be sent
   back to partner's shopfloor backend, please use shopfloor_service pytest
   and ActivateRegCode API instead.

Additionally, if argument ``server_url`` is specified, this test will update the
stored 'default factory server URL' so all following tests connecting to factory
server via ``server_proxy.GetServerProxy()`` will use the new URL.

``server_url`` supports few different input:

- If a string is given, that is interpreted as simple URL. For example,
  ``"http://10.3.0.11:8080/"``.
- If a mapping (dict) is given, take key as network IP/CIDR and value as URL.
  For example, ``{"10.3.0.0/24": "http://10.3.0.11:8080"}``

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
To connect to default server and sync time, event logs, and update software,
add this in test list::

  {
    "pytest_name": "sync_factory_server"
  }

To only sync time and logs, and never update software (useful for stations)::

  {
    "pytest_name": "sync_factory_server",
    "args": {
      "update_toolkit": false
    }
  }

To sync time and logs, and then upload a report::

  {
    "pytest_name": "sync_factory_server",
    "args": {
      "upload_report": true
    }
  }

To override default factory server URL for all tests, change the
``default_factory_server_url`` in test list constants::

  {
    "constants": {
      "default_factory_server_url": "http://192.168.3.11:8080"
    }
  }

It is also possible to override and create one test item using different factory
server URL, and all tests after that::

  {
    "pytest_name": "sync_factory_server",
    "args": {
      "server_url": "http://192.168.3.11:8080"
    }
  }

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

To implement "auto-detect factory server by received DHCP IP address", specify a
mapping object with key set to "IP/CIDR" and value set to server URL::

  {
    "constants": {
      "default_factory_server_url": {
        "192.168.3.0/24": "http://192.168.3.11:8080",
        "10.3.0.0/24": "http://10.3.0.11:8080",
        "10.1.0.0/16": "http://10.1.2.10:8080"
      }
    }
  }
"""

import logging
import threading
import time

from cros.factory.device import device_utils
from cros.factory.gooftool import commands
from cros.factory.goofy import updater
from cros.factory.test import device_data
from cros.factory.test.i18n import _
from cros.factory.test.rules import registration_codes
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import time_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import log_utils
from cros.factory.utils import sync_utils


ID_TEXT_INPUT_URL = 'text_input_url'
ID_BUTTON_EDIT_URL = 'button_edit_url'

EVENT_SET_URL = 'event_set_url'
EVENT_CANCEL_SET_URL = 'event_cancel_set_url'
EVENT_DO_SET_URL = 'event_do_set_url'


class Report:
  """A structure for reports uploaded to factory server."""

  def __init__(self, serial_number, blob, station):
    self.serial_number = serial_number
    self.blob = blob
    self.station = station


class SyncFactoryServer(test_case.TestCase):
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
      Arg('upload_reg_codes', bool, 'Upload registration codes to server.',
          default=False),
      Arg('upload_report', bool, 'Upload a factory report to factory server.',
          default=False),
      Arg('report_stage', str, 'Stage of report to upload.', default=None),
      Arg('report_serial_number_name', str,
          'Name of serial number to use for report file name to use.',
          default=None),
      Arg('server_url', (str, dict),
          'Set and keep new factory server URL.',
          default=None),
  ]

  def setUp(self):
    self.server = None
    self.do_setup_url = threading.Event()
    self.allow_edit_url = True
    self.event_url_set = threading.Event()
    self.goofy = state.GetInstance()
    self.report = Report(None, None, self.args.report_stage)
    self.dut = device_utils.CreateDUTInterface()
    self.station = device_utils.CreateStationInterface()

  @staticmethod
  def CreateButton(node_id, message, on_click):
    return [
        '<button type="button" id="%s" onclick=%r>' % (node_id, on_click),
        message, '</button>'
    ]

  def CreateChangeURLButton(self):
    return self.CreateButton(
        ID_BUTTON_EDIT_URL,
        _('Change URL'),
        'this.disabled = true; window.test.sendTestEvent("%s");' %
        EVENT_DO_SET_URL)

  def OnButtonSetClicked(self, event):
    self.ChangeServerURL(event.data)
    self.do_setup_url.clear()
    self.event_url_set.set()

  def OnButtonCancelClicked(self, event):
    del event  # Unused.
    self.do_setup_url.clear()
    self.event_url_set.set()

  def OnButtonEditClicked(self, event):
    del event  # Unused.
    self.do_setup_url.set()
    self.ui.SetHTML(
        _('Please wait few seconds to edit...'), id=ID_BUTTON_EDIT_URL)

  def EditServerURL(self):
    current_url = server_proxy.GetServerURL() or ''

    if current_url:
      prompt = []
    else:
      prompt = [
          '<span class="warning_label">',
          _('No factor server URL configured.'),
          '</span><span class="warning_message">',
          # TODO(hungte) Add message when we can't connect to factory server.
          _('For debugging or development, '
            'enter engineering mode to start individual tests.'),
          '</span>'
      ]

    self.ui.SetState([
        prompt,
        _('Change server URL: '),
        '<input type="text" id="%s" value="%s"/>' % (ID_TEXT_INPUT_URL,
                                                     current_url), '<span>',
        self.CreateButton('btnSet',
                          _('Set'), 'window.test.sendTestEvent("%s", '
                          'document.getElementById("%s").value)' %
                          (EVENT_SET_URL, ID_TEXT_INPUT_URL)),
        self.CreateButton(
            'btnCancel',
            _('Cancel'),
            'window.test.sendTestEvent("%s")' % EVENT_CANCEL_SET_URL), '</span>'
    ])

  def DetectServerURL(self):
    expected_networks = list(self.args.server_url)
    label_connect = _('Please connect to network...')
    label_status = _('Expected network: {networks}', networks=expected_networks)

    while True:
      new_url = self.FindServerURL(self.args.server_url)
      if new_url:
        break
      # Collect current networks. The output format is DEV STATUS NETWORK.
      output = self.station.CallOutput(['ip', '-f', 'inet', '-br', 'addr'])
      networks = [entry.split()[2] for entry in output.splitlines()
                  if ' UP ' in entry]
      self.ui.SetState([
          label_connect, label_status,
          _('Current networks: {networks}', networks=networks)
      ])
      self.Sleep(0.5)

    self.ChangeServerURL(new_url)
    self.do_setup_url.clear()

  def Ping(self):
    if self.do_setup_url.is_set():
      self.event_url_set.clear()
      self.EditServerURL()
      sync_utils.EventWait(self.event_url_set)

    self.ui.SetState(
        [_('Trying to reach server...'),
         self.CreateChangeURLButton()])
    self.server = server_proxy.GetServerProxy(timeout=self.args.timeout_secs)

    if self.do_setup_url.is_set():
      raise Exception('Edit URL clicked.')

    self.ui.SetState(
        [_('Trying to check server protocol...'),
         self.CreateChangeURLButton()])
    self.server.Ping()
    self.allow_edit_url = False

  def ChangeServerURL(self, new_server_url):
    server_url = server_proxy.GetServerURL() or ''

    if new_server_url and new_server_url != server_url:
      server_proxy.SetServerURL(new_server_url.rstrip('/'))
      # Read again because server_proxy module may normalize it.
      new_server_url = server_proxy.GetServerURL()
      session.console.info(
          'Factory server URL has been changed from [%s] to [%s].',
          server_url, new_server_url)
      server_url = new_server_url

    self.ui.SetInstruction(_('Server URL: {server_url}', server_url=server_url))
    if not server_url:
      self.do_setup_url.set()

  def FlushTestlog(self):
    # TODO(hungte) goofy.FlushTestlog should reload factory_server_url.
    result = False
    while not result:
      result, progress = self.goofy.FlushTestlog(timeout=2)
      self.ui.SetState(
          _('Flush Test Log: Progress = <br>{progress}', progress=progress))

  def CreateReport(self):
    self.ui.SetState(_('Collecting report data...'))
    self.report.blob = commands.CreateReportArchiveBlob()
    self.ui.SetState(_('Getting serial number...'))
    self.report.serial_number = device_data.GetSerialNumber(
        self.args.report_serial_number_name or
        device_data.NAME_SERIAL_NUMBER)

  def UploadReport(self):
    self.server.UploadReport(
        self.report.serial_number, self.report.blob, None, self.report.station)

  def UploadRegCodes(self):
    """Uploads registration codes to factory server.

    The registration codes should be sent in format from http://goto/nkjyr.
    """
    hwid = device_data.GetDeviceData(
        device_data.KEY_HWID, self.dut.CallOutput('crossystem hwid'))
    if not hwid:
      raise Exception('Need HWID before uploading registration codes.')

    board = hwid.partition(' ')[0]
    ubind = device_data.GetDeviceData(device_data.KEY_VPD_USER_REGCODE)
    gbind = device_data.GetDeviceData(device_data.KEY_VPD_GROUP_REGCODE)
    for label, value in ('user', ubind), ('group', gbind):
      if not value:
        raise Exception('Missing %s registration codes in device data (%r).' %
                        (label, value))

    registration_codes.CheckRegistrationCode(ubind)
    registration_codes.CheckRegistrationCode(gbind)
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    entry = [board, ubind, gbind, timestamp, hwid]
    self.server.UploadCSVEntry('registration_code_log', entry)

  def UpdateToolkit(self):
    unused_toolkit_version, has_update = updater.CheckForUpdate(
        self.args.timeout_secs)
    if not has_update:
      return

    # Update necessary. Note that updateFactory() will kill this test.
    if not self.args.update_without_prompt:
      # Display message and require update.
      self.ui.SetState(
          _('A software update is available. Press SPACE to update.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self.ui.CallJSFunction('window.test.updateFactory')

    # Let this test sleep forever, and wait for either the SPACE event, or the
    # factory update to complete. Note that we want the test to neither pass or
    # fail, so we won't be accidentally running other tests when the
    # updateFactory is running.
    self.WaitTaskEnd()

  @staticmethod
  def IsDynamicServer(url_spec):
    """Returns if the url_spec is something to be dynamically configured."""
    return isinstance(url_spec, dict) and url_spec

  def FindServerURL(self, url_spec):
    """Try to return a single normalized URL from given specification.

    It is very often that partner may want to deploy multiple servers with
    different IP, and expect DUT to connect right server according to the DHCP
    IP it has received.

    This function tries to parse argument url_spec and find a "best match
    URL" for it.

    Args:
      url_spec: a simple string as URL or a mapping from IP/CIDR to URL.

    Returns:
      A single URL string that best matches given spec.
    """
    if not self.IsDynamicServer(url_spec):
      return url_spec

    # Sort by CIDR so smaller network matches first.
    networks = sorted(
        url_spec, reverse=True, key=lambda k: int(k.partition('/')[-1] or 0))
    for ip_cidr in networks:
      # The command returned zero even if no interfaces match.
      if self.station.CallOutput(['ip', 'addr', 'show', 'to', ip_cidr]):
        return url_spec[ip_cidr]

    return url_spec.get('default', '')

  def runTest(self):
    self.ui.SetInstruction(_('Preparing...'))
    retry_secs = self.args.first_retry_secs

    self.event_loop.AddEventHandler(EVENT_SET_URL, self.OnButtonSetClicked)
    self.event_loop.AddEventHandler(EVENT_CANCEL_SET_URL,
                                    self.OnButtonCancelClicked)
    self.event_loop.AddEventHandler(EVENT_DO_SET_URL, self.OnButtonEditClicked)

    # Setup tasks to perform.
    tasks = [(_('Ping'), self.Ping)]

    if self.IsDynamicServer(self.args.server_url):
      # Server URL must be confirmed before Ping.
      tasks = [(_('Detect Server URL'), self.DetectServerURL)] + tasks

    if self.args.sync_time:
      def SyncTime():
        if not time_utils.SyncTimeWithFactoryServer():
          raise Exception('Failed to sync time with factory server')
      tasks += [(_('Sync time'), SyncTime)]

    if self.args.sync_event_logs:
      tasks += [(_('Flush Event Logs'), self.goofy.FlushEventLogs)]

    if self.args.flush_testlog:
      tasks += [(_('Flush Test Log'), self.FlushTestlog)]

    if self.args.upload_report:
      tasks += [(_('Create Report'), self.CreateReport)]
      tasks += [(_('Upload report'), self.UploadReport)]

    if self.args.upload_reg_codes:
      tasks += [(_('Upload Reg Codes'), self.UploadRegCodes)]

    if self.args.update_toolkit:
      tasks += [(_('Update Toolkit'), self.UpdateToolkit)]
    else:
      session.console.info('Toolkit update is disabled.')

    # Setup new server URL
    server_proxy.ValidateServerConfig()
    self.ChangeServerURL(self.FindServerURL(self.args.server_url))

    # It's very often that a DUT under FA is left without network connected for
    # hours to days, so we should not log (which will increase TestLog events)
    # if the exception string is not changed.
    logger = log_utils.NoisyLogger(
        lambda fault, prompt: logging.exception(prompt, fault))

    self.ui.DrawProgressBar(len(tasks))

    for label, task in tasks:
      while True:
        try:
          logging.info('Running task: %s.', label['en-US'])
          self.ui.SetState(_('Running task: {label}', label=label))
          task()
          logging.info('Server task finished: %s.', label['en-US'])
          self.ui.SetState([
              '<span style="color: green">',
              _('Server Task Finished: {label}', label=label), '</span>'
          ])
          self.Sleep(0.5)
          break
        except server_proxy.Fault as f:
          message = f.faultString
          logger.Log(message, 'Server fault with message: %s')
        except Exception:
          message = debug_utils.FormatExceptionOnly()
          logger.Log(message, 'Unable to sync with server: %s')

        logging.info('Waiting for retrying task: %s.', label['en-US'])
        msg = lambda time_left, label_: _(
            'Task <b>{label}</b> failed, retry in {time_left} seconds...',
            time_left=time_left,
            label=label_)
        edit_url_button = (['<p>', self.CreateChangeURLButton(), '</p>']
                           if self.allow_edit_url else '')
        self.ui.SetState([
            '<span id="retry">',
            msg(retry_secs, label), '</span>', edit_url_button,
            '<p><textarea rows=25 cols=90 readonly class="sync-detail">',
            test_ui.Escape(message, False), '</textarea>'
        ])

        try:
          # sync_utils.EventWait() may log timeout message every second, so we
          # disable logging.INFO temporarily.
          logging.disable(logging.INFO)
          for sec in range(retry_secs):
            if sync_utils.EventWait(self.do_setup_url, timeout=1):
              break
            self.ui.SetHTML(msg(retry_secs - sec - 1, label), id='retry')
        finally:
          logging.disable(logging.NOTSET)
        retry_secs = min(2 * retry_secs, self.args.retry_secs)

      self.ui.AdvanceProgress()
