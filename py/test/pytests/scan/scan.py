# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Prompts the operator to input a string of data."""

from __future__ import print_function
import logging
import re
import socket
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event as test_event
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test.fixture import bft_fixture
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.tools import ghost
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import process_utils


class Scan(unittest.TestCase):
  """The main class for this pytest."""
  ARGS = (i18n_arg_utils.BackwardCompatibleI18nArgs(
      'label',
      'Name of the ID or serial number being scanned, e.g., "MLB serial number"'
  ) + [
      Arg('aux_table_name', str,
          'Name of the auxiliary table containing the device', optional=True),
      Arg('event_log_key', str, 'Key to use for event log', optional=True),
      Arg('shared_data_key', str,
          'Key to use to store in scanned value in shared data',
          optional=True),
      Arg('device_data_key', str,
          'Key to use to store in scanned value in device data',
          optional=True),
      Arg('dut_data_key', str,
          'Key to use to store in scanned value in DUT.',
          optional=True),
      Arg('ro_vpd_key', str,
          'Key to use to store in scanned value in RO VPD', optional=True),
      Arg('rw_vpd_key', str,
          'Key to use to store in scanned value in RW VPD', optional=True),
      Arg('regexp', str, 'Regexp that the scanned value must match',
          optional=True),
      Arg('check_device_data_key', str,
          'Checks that the given value in device data matches the scanned '
          'value',
          optional=True),
      Arg('bft_scan_fixture_id', bool, 'True to scan BFT fixture ID.',
          default=False),
      Arg('bft_scan_barcode', bool, 'True to trigger BFT barcode scanner.',
          default=False),
      Arg('bft_save_barcode', bool,
          'True to trigger BFT barcode scanner and save in BFT.',
          default=False),
      Arg('bft_get_barcode', (bool, str),
          'True to get barcode from BFT. BFT stores barcode in advance so this '
          'obtains barcode immidiately. If a string is given, will override '
          'default path (`nuc_dut_serial_path`)', default=False),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, default=None,
          optional=True),
      Arg('barcode_scan_interval_secs', (int, float),
          "Interval for repeatedly trigger BFT's barcode scaner",
          default=2.0),
      Arg('match_the_last_few_chars', int,
          'This is for OP to manually input last few SN chars based on the\n'
          'sticker on machine to make sure SN in VPD matches sticker SN.',
          default=0),
      Arg('ignore_case', bool, 'True to ignore case from input.',
          default=False),
      Arg('value_assigned', str,
          'If not None, use the value to fill the key.', optional=True),
      Arg('reconnect_ghost', bool,
          'Reconnect ghost to update machine ID', default=False, optional=True)
  ])

  def HandleScanValue(self, event):
    def SetError(label):
      logging.info('Scan error: %r', label['en-US'])
      self.ui.SetHTML('<span class="test-error">' +
                      i18n_test_ui.MakeI18nLabel(label) +
                      '</span>',
                      id='scan-status')
      self.ui.RunJS('$("scan-value").disabled = false;'
                    '$("scan-value").value = ""')
      self.ui.SetFocus('scan-value')

    self.ui.RunJS('$("scan-value").disabled = true')
    scan_value = event.data.strip()
    if self.args.ignore_case:
      scan_value = scan_value.upper()
    esc_scan_value = test_ui.Escape(scan_value)
    if not scan_value:
      return SetError(_('The scanned value is empty.'))
    if self.args.regexp:
      match = re.match(self.args.regexp, scan_value)
      if not match or match.group(0) != scan_value:
        return SetError(
            i18n.StringFormat(
                _('The scanned value "{value}" does not match '
                  'the expected format.'),
                value=esc_scan_value))

    if self.args.aux_table_name:
      try:
        shopfloor.select_aux_data(self.args.aux_table_name,
                                  scan_value)
      except shopfloor.ServerFault:
        logging.exception('select_aux_data failed')
        return SetError(
            i18n.StringFormat(
                _('The scanned value "{value}" is not a known {label}.'),
                value=esc_scan_value, label=self.args.label))
      except socket.error as e:
        logging.exception('select_aux_data failed')
        return SetError(
            i18n.StringFormat(
                _('Unable to contact shopfloor server: {exception}'),
                exception=e))
      except:  # pylint: disable=bare-except
        logging.exception('select_aux_data failed')
        return SetError(i18n.NoTranslation(debug_utils.FormatExceptionOnly()))

    if self.args.event_log_key:
      event_log.Log('scan', key=self.args.event_log_key, value=scan_value)

    if self.args.shared_data_key:
      factory.set_shared_data(self.args.shared_data_key,
                              scan_value)

    if self.args.device_data_key:
      shopfloor.UpdateDeviceData({self.args.device_data_key: scan_value})

    if self.args.dut_data_key:
      self.dut.storage.UpdateDict({self.args.dut_data_key: scan_value})

    if self.args.check_device_data_key:
      expected_value = shopfloor.GetDeviceData().get(
          self.args.check_device_data_key)

      if self.args.match_the_last_few_chars != 0:
        expected_value = expected_value[-self.args.match_the_last_few_chars:]

      if expected_value != scan_value:
        logging.error('Expected %r but got %r', expected_value, scan_value)

        # Show expected value only in engineering mode, so the user
        # can't fake it.
        esc_expected_value = test_ui.Escape(expected_value or 'None')
        return SetError(
            i18n.StringFormat(
                _('The scanned value "{value}" does not match '
                  'the expected value <span class=test-engineering-mode-only>'
                  '"{expected_value}"</span>.'),
                value=esc_scan_value, expected_value=esc_expected_value))

    if self.args.rw_vpd_key or self.args.ro_vpd_key:
      self.ui.SetHTML(
          ' '.join([
              i18n_test_ui.MakeI18nLabel('Writing to VPD. Please wait...'),
              test_ui.SPINNER_HTML_16x16
          ]),
          id='scan-status')
      try:
        if self.args.rw_vpd_key:
          self.dut.vpd.rw.Update({self.args.rw_vpd_key: scan_value})
        if self.args.ro_vpd_key:
          self.dut.vpd.ro.Update({self.args.ro_vpd_key: scan_value})
      except:  # pylint: disable=bare-except
        logging.exception('Setting VPD failed')
        return SetError(debug_utils.FormatExceptionOnly())

    self.ui.event_client.post_event(
        test_event.Event(test_event.Event.Type.UPDATE_SYSTEM_INFO))
    self.ui.Pass()

  def setUp(self):
    i18n_arg_utils.ParseArg(self, 'label')
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI()
    self.auto_scan_timer = None
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

  def tearDown(self):
    if self.fixture:
      self.fixture.Disconnect()

    if self.auto_scan_timer:
      self.auto_scan_timer.cancel()

    if self.args.reconnect_ghost:
      self.KickGhost()

  def ScanBarcode(self):
    while True:
      self.fixture.ScanBarcode()
      time.sleep(self.args.barcode_scan_interval_secs)

  def BFTScanSaveBarcode(self):
    while True:
      self.fixture.TriggerScanner()
      time.sleep(self.args.barcode_scan_interval_secs)

  def KickGhost(self):
    server = ghost.GhostRPCServer()
    try:
      server.Reconnect()
    except socket.error as e:
      logging.exception(str(e))

  def runTest(self):
    template = ui_templates.OneSection(self.ui)

    template.SetTitle(
        i18n_test_ui.MakeI18nLabel('Scan {label}', label=self.args.label))

    template.SetState(
        i18n_test_ui.MakeI18nLabel(
            'Please scan the {label} and press ENTER.',
            label=self.args.label) +
        '<br><input id="scan-value" type="text" size="20">'
        '<br>&nbsp;'
        '<p id="scan-status">&nbsp;')
    self.ui.RunJS("document.getElementById('scan-value').focus()")
    self.ui.BindKeyJS(
        test_ui.ENTER_KEY,
        'window.test.sendTestEvent("scan_value",'
        'document.getElementById("scan-value").value)')
    self.ui.AddEventHandler('scan_value', self.HandleScanValue)

    if self.args.value_assigned is not None:
      self.ui.RunJS(
          'window.test.sendTestEvent("scan_value", "%s")' %
          self.args.value_assigned)
    elif self.args.bft_scan_fixture_id:
      logging.info('Getting fixture ID...')
      fixture_id = self.fixture.GetFixtureId()
      self.ui.RunJS(
          'window.test.sendTestEvent("scan_value", "%d")' % fixture_id)
    elif self.args.bft_scan_barcode:
      logging.info('Triggering barcode scanner...')
      process_utils.StartDaemonThread(target=self.ScanBarcode)
    elif self.args.bft_save_barcode:
      logging.info('Triggering barcode scanner...')
      process_utils.StartDaemonThread(target=self.BFTScanSaveBarcode)
    elif self.args.bft_get_barcode:
      logging.info('Getting barcode from BFT...')
      saved_barcode_path = None
      if isinstance(self.args.bft_get_barcode, str):
        saved_barcode_path = self.args.bft_get_barcode
      barcode = self.fixture.ScanBarcode(saved_barcode_path)
      self.ui.RunJS(
          'window.test.sendTestEvent("scan_value", "%s")' % barcode)

    self.ui.Run()
