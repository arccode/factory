# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Scans barcode and saves it to a specific file."""

from __future__ import print_function

import logging
import re
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.fixture.whale import whale_bft_fixture
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg

_CHECK_BARCODE_SECS = 0.3


class BarcodeScanToFileTest(unittest.TestCase):
  """Scans barcode and saves it to a specific file."""
  ARGS = (i18n_arg_utils.BackwardCompatibleI18nArgs(
      'label', 'Name of the barcode to scan'
  ) + [
      Arg('regexp', str, 'Regexp that the scanned value must match',
          optional=True),
      Arg('ignore_case', bool, 'True to ignore case from input.',
          default=False),
      Arg('save_path', str, 'The file path of saving barcode'),
      Arg('bft_params', dict,
          'Parameters to initialize WhaleBFTFixture. It is a dict which '
          'contains at least "host" and "port" that points to BeagleBone '
          'servod.',
          optional=True)])

  def ShowError(self, message):
    logging.info('Scan error: %r', message['en-US'])
    error_message = i18n_test_ui.MakeI18nLabel(message)
    self.ui.SetHTML(
        '<span class="test-error">%s</span>' % error_message,
        id='scan-status')
    self.ui.RunJS('$("scan-value").disabled = false;'
                  '$("scan-value").value = ""')
    self.ui.SetFocus('scan-value')

  def HandleScanValue(self, event):
    self.ui.RunJS('$("scan-value").disabled = true')
    scan_value = event.data.strip()

    # check scan value
    if self.args.ignore_case:
      scan_value = scan_value.upper()
    esc_scan_value = test_ui.Escape(scan_value)
    if not scan_value:
      self.ShowError(_('The scanned value is empty.'))
      return
    if self.args.regexp:
      match = re.match(self.args.regexp, scan_value)
      if not match or match.group(0) != scan_value:
        self.ShowError(i18n.StringFormat(
            _('The scanned value "{scan_value}" does not match '
              'the expected format.'), scan_value=esc_scan_value))
        return

    # save scan value
    factory.console.info('Save barcode %s at: %s', esc_scan_value,
                         self.args.save_path)

    dirname = self.dut.path.dirname(self.args.save_path)
    if not self.dut.path.exists(dirname):
      self.dut.CheckCall(['mkdir', '-p', dirname])
    self.dut.WriteFile(self.args.save_path, esc_scan_value)

    self.ui.Pass()

  def setUp(self):
    i18n_arg_utils.ParseArg(self, 'label')
    self.ui = test_ui.UI()
    self.dut = device_utils.CreateDUTInterface()
    if self.args.bft_params is not None:
      self._bft = whale_bft_fixture.WhaleBFTFixture()
      self._bft.Init(**self.args.bft_params)
    else:
      self._bft = None

    # clean barcode file first
    self.dut.CheckCall(['rm', '-f', self.args.save_path])

  def runTest(self):
    template = ui_templates.OneSection(self.ui)

    template.SetTitle(
        i18n_test_ui.MakeI18nLabel('Scan {label}', label=self.args.label))

    template.SetState(
        i18n_test_ui.MakeI18nLabel(
            'Please scan the {label} and press ENTER.', label=self.args.label) +
        '<br><input id="scan-value" type="text" size="20" tabindex="1">'
        '<p id="scan-status">')
    self.ui.SetFocus('scan-value')
    self.ui.BindKeyJS(
        '\r',
        ('window.test.sendTestEvent("scan_value",'
         'document.getElementById("scan-value").value)'))
    self.ui.AddEventHandler('scan_value', self.HandleScanValue)

    if self._bft:
      self.ui.Run(blocking=False)
      while not self.dut.path.exists(self.args.save_path):
        self._bft.TriggerScanner()
        time.sleep(_CHECK_BARCODE_SECS)
    else:
      # manual scan
      self.ui.Run()
