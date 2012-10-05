# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import socket
import unittest


from cros.factory.event_log import EventLog
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg


class Scan(unittest.TestCase):
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
    Arg('regexp', str,
        'Regexp that the scanned value must match', optional=True),
  ]

  def HandleScanValue(self, event):
    def SetError(label_en, label_zh=None):
      logging.info('Scan error: %r', label_en)
      self.ui.SetHTML(test_ui.MakeLabel(label_en, label_zh),
                      id='scan-error')
      self.ui.RunJS('$("scan-value").focus();'
                    '$("scan-value").value = ""')

    scan_value = event.data.strip()
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
      EventLog.ForAutoTest().Log('scan',
                                 key=self.args.event_log_key,
                                 value=scan_value)

    if self.args.shared_data_key:
      factory.set_shared_data(self.args.shared_data_key,
                              scan_value)

    self.ui.Pass()

  def setUp(self):
    self.ui = test_ui.UI()

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
        '<p id="scan-error" class="test-error">&nbsp;')
    self.ui.RunJS("document.getElementById('scan-value').focus()")
    self.ui.BindKeyJS(
        '\r',
        ('window.test.sendTestEvent("scan_value",'
         'document.getElementById("scan-value").value)'))
    self.ui.AddEventHandler('scan_value', self.HandleScanValue)
    self.ui.Run()
