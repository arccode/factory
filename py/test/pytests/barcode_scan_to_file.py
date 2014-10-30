# -*- mode: python; coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Scans barcode and saves it to a specific file."""

from __future__ import print_function

import logging
import os
import re
import unittest
import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates


class BarcodeScanToFileTest(unittest.TestCase):
  """Scans barcode and saves it to a specific file."""
  ARGS = [
    Arg('label_en', str, 'Name of the barcode to scan'),
    Arg('label_zh', str,
        'Chinese name of barcode being scanned '
        '(defaults to the same as the English label)'),
    Arg('regexp', str,
        'Regexp that the scanned value must match', optional=True),
    Arg('ignore_case', bool,
        'True to ignore case from input.', default=False),
    Arg('save_path', str,
        'The file path of saving barcode'),
  ]

  def ShowError(self, message, message_zh=None):
    logging.info('Scan error: %r', message)
    self.ui.SetHTML('<span class="test-error">' +
        test_ui.MakeLabel(message, message_zh) +
        '</span>',
        id='scan-status')
    self.ui.RunJS('$("scan-value").focus();'
        '$("scan-value").value = "";'
        '$("scan-value").disabled = false')

  def HandleScanValue(self, event):
    self.ui.RunJS('$("scan-value").disabled = true')
    scan_value = event.data.strip()

    # check scan value
    if self.args.ignore_case:
      scan_value = scan_value.upper()
    esc_scan_value = test_ui.Escape(scan_value)
    if not scan_value:
      return self.ShowError('The scanned value is empty.',
          '扫描编号是空的。')
    if self.args.regexp:
      match = re.match(self.args.regexp, scan_value)
      if not match or match.group(0) != scan_value:
        return self.ShowError(
            'The scanned value "%s" does not match '
            'the expected format.' % esc_scan_value,
            '所扫描的编号「%s」格式不对。' % esc_scan_value)

    # create directory
    dirname = os.path.dirname(self.args.save_path)
    if not os.path.exists(dirname):
      os.makedirs(dirname)

    # save scan value
    factory.console.info('Save barcode at: ' + self.args.save_path)
    with open(self.args.save_path, 'w') as f:
      f.write(esc_scan_value)

    self.ui.Pass()

  def setUp(self):
    self.ui = test_ui.UI()

  def tearDown(self):
    pass

  def runTest(self):
    template = ui_templates.OneSection(self.ui)

    label_zh = self.args.label_zh or self.args.label_en
    template.SetTitle(test_ui.MakeLabel(
        'Scan %s' % self.args.label_en.title(),
        '扫描%s' % label_zh))

    template.SetState(
        test_ui.MakeLabel(
            'Please scan the %s and press ENTER.' % self.args.label_en,
            '请扫描%s后按下 ENTER。' % label_zh) +
        '<br><input id="scan-value" type="text" size="20" tabindex="1">'
        '<p id="scan-status">')
    self.ui.RunJS("document.getElementById('scan-value').focus()")
    self.ui.BindKeyJS(
        '\r',
        ('window.test.sendTestEvent("scan_value",'
         'document.getElementById("scan-value").value)'))
    self.ui.AddEventHandler('scan_value', self.HandleScanValue)

    self.ui.Run()
