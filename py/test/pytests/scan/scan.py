# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Prompts the operator to input a string of data."""

import logging
import re
import socket
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.system import vpd
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.fixture.bft_fixture import (CreateBFTFixture,
                                                   TEST_ARG_HELP)
from cros.factory.test.utils import StartDaemonThread


class Scan(unittest.TestCase):
  """The main class for this pytest."""
  ARGS = [
    Arg('aux_table_name', str,
        'Name of the auxiliary table containing the device',
        optional=True),
    Arg('label_en', str,
        'Name of the ID or serial number being scanned, e.g., '
        '"MLB serial number"'),
    Arg('label_zh', str,
        'Chinese name of the ID or serial number being scanned '
        '(defaults to the same as the English label)'),
    Arg('event_log_key', str,
        'Key to use for event log', optional=True),
    Arg('shared_data_key', str,
        'Key to use to store in scanned value in shared data', optional=True),
    Arg('device_data_key', str,
        'Key to use to store in scanned value in device data', optional=True),
    Arg('rw_vpd_key', str,
        'Key to use to store in scanned value in RW VPD', optional=True),
    Arg('regexp', str,
        'Regexp that the scanned value must match', optional=True),
    Arg('check_device_data_key', str,
        'Checks that the given value in device data matches the scanned value',
        optional=True),
    Arg('bft_scan_fixture_id', bool,
        'True to scan BFT fixture ID.', default=False),
    Arg('bft_scan_barcode', bool,
        'True to trigger BFT barcode scanner.', default=False),
    Arg('bft_fixture', dict, TEST_ARG_HELP, default=None, optional=True),
    Arg('barcode_scan_interval_secs', (int, float),
        'Interval for repeatedly trigger BFT\'s barcode scaner',
        default=2.0),
    Arg('match_the_last_few_chars', int,
        'This is for OP to manually input last few SN chars based on the\n'
        'sticker on machine to make sure SN in VPD matches sticker SN.',
        default=0),
    Arg('ignore_case', bool,
        'True to ignore case from input.', default=False),
  ]

  def HandleScanValue(self, event):
    def SetError(label_en, label_zh=None):
      logging.info('Scan error: %r', label_en)
      self.ui.SetHTML('<span class="test-error">' +
                      test_ui.MakeLabel(label_en, label_zh) +
                      '</span>',
                      id='scan-status')
      self.ui.RunJS('$("scan-value").focus();'
                    '$("scan-value").value = "";'
                    '$("scan-value").disabled = false')

    self.ui.RunJS('$("scan-value").disabled = true')

    scan_value = event.data.strip()
    if self.args.ignore_case:
      scan_value = scan_value.upper()
    esc_scan_value = test_ui.Escape(scan_value)
    if not scan_value:
      return SetError('The scanned value is empty.',
                      '掃描編號是空的。')
    if self.args.regexp:
      match = re.match(self.args.regexp, scan_value)
      if not match or match.group(0) != scan_value:
        return SetError(
            'The scanned value "%s" does not match '
            'the expected format.' % esc_scan_value,
            '所掃描的編號「%s」格式不對。' % esc_scan_value)

    if self.args.aux_table_name:
      try:
        shopfloor.select_aux_data(self.args.aux_table_name,
                                  scan_value)
      except shopfloor.ServerFault:
        logging.exception('select_aux_data failed')
        return SetError(
            'The scanned value "%s" is not a known %s.' % (
                esc_scan_value, self.args.label_en),
            '所掃描的編號「%s」不是已知的%s。' % (
                esc_scan_value, self.args.label_zh))
      except socket.error as e:
        logging.exception('select_aux_data failed')
        return SetError(
            'Unable to contact shopfloor server: %s' % e,
            '連不到 shopfloor server: %s' % e)
      except:  # pylint: disable=W0622
        logging.exception('select_aux_data failed')
        return SetError(utils.FormatExceptionOnly())
      factory.get_state_instance().UpdateSkippedTests()

    if self.args.event_log_key:
      Log('scan', key=self.args.event_log_key, value=scan_value)

    if self.args.shared_data_key:
      factory.set_shared_data(self.args.shared_data_key,
                              scan_value)

    if self.args.device_data_key:
      shopfloor.UpdateDeviceData({self.args.device_data_key: scan_value})
      factory.get_state_instance().UpdateSkippedTests()

    if self.args.check_device_data_key:
      expected_value = shopfloor.GetDeviceData().get(
          self.args.check_device_data_key)

      if self.args.match_the_last_few_chars != 0:
        expected_value = expected_value[-self.args.match_the_last_few_chars:]

      if expected_value != scan_value:
        logging.error("Expected %r but got %r", expected_value, scan_value)

        # Show expected value only in engineering mode, so the user
        # can't fake it.
        esc_expected_value = (
            test_ui.Escape(expected_value or "None"))
        return SetError(
            'The scanned value "%s" does not match '
            'the expected value'
            '<span class=test-engineering-mode-only> "%s".</span>' % (
                esc_scan_value, esc_expected_value),
            u'所掃描的編號「%s」不搭配所期望的編號'
            u'<span class=test-engineering-mode-only>「%s」</span>。' % (
                esc_scan_value, esc_expected_value))

    if self.args.rw_vpd_key:
      self.ui.SetHTML(
          test_ui.MakeLabel('Writing to VPD. Please wait…',
                            '正在写到 VPD，请稍等…') +
          ' ' + test_ui.SPINNER_HTML_16x16,
          id='scan-status')
      try:
        vpd.rw.Update({self.args.rw_vpd_key: scan_value})
      except:  # pylint: disable=W0702
        logging.exception('Setting VPD failed')
        return SetError(utils.FormatExceptionOnly())

    self.ui.event_client.post_event(Event(Event.Type.UPDATE_SYSTEM_INFO))
    self.ui.Pass()

  def setUp(self):
    self.ui = test_ui.UI()
    self.auto_scan_timer = None
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = CreateBFTFixture(**self.args.bft_fixture)

  def tearDown(self):
    if self.fixture:
      self.fixture.Disconnect()

    if self.auto_scan_timer:
      self.auto_scan_timer.cancel()

  def ScanBarcode(self):
    while True:
      self.fixture.ScanBarcode()
      time.sleep(self.args.barcode_scan_interval_secs)

  def runTest(self):
    template = ui_templates.OneSection(self.ui)

    if not self.args.label_zh:
      self.args.label_zh = self.args.label_en

    template.SetTitle(test_ui.MakeLabel(
        'Scan %s' % self.args.label_en.title(),
        '扫描%s' % self.args.label_zh))

    template.SetState(
        test_ui.MakeLabel(
            'Please scan the %s and press ENTER.' % self.args.label_en,
            '请扫描%s後按下 ENTER。' % (
                self.args.label_zh or self.args.label_en)) +
        '<br><input id="scan-value" type="text" size="20">'
        '<br>&nbsp;'
        '<p id="scan-status">&nbsp;')
    self.ui.RunJS("document.getElementById('scan-value').focus()")
    self.ui.BindKeyJS(
        '\r',
        ('window.test.sendTestEvent("scan_value",'
         'document.getElementById("scan-value").value)'))
    self.ui.AddEventHandler('scan_value', self.HandleScanValue)

    if self.args.bft_scan_fixture_id:
      logging.info('Getting fixture ID...')
      fixture_id = self.fixture.GetFixtureId()
      self.ui.RunJS(
        'window.test.sendTestEvent("scan_value","%d")' % fixture_id)
    elif self.args.bft_scan_barcode:
      logging.info('Triggering barcode scanner...')
      StartDaemonThread(target=self.ScanBarcode)

    self.ui.Run()
