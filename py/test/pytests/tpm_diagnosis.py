# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs tpm_selftest to perform TPM self-diagnosis."""

import os
import threading

from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class TpmDiagnosisTest(test_case.TestCase):
  ARGS = [
      Arg('tpm_selftest', str, 'Path of tpm_selftest program.',
          default='/usr/local/sbin/tpm_selftest'),
      Arg('tpm_args', list, 'List of tpm_selftest args.',
          default=['-l', 'debug']),
      Arg('success_pattern', str, 'Pattern of success.',
          default='tpm_selftest succeeded')
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self.assertTrue(os.path.isfile(self.args.tpm_selftest),
                    msg='%s is missing.' % self.args.tpm_selftest)

  def runTest(self):
    """Runs tpm_selftest.

    It shows diagnosis result on factory UI.
    """
    success = threading.Event()
    def _Callback(line):
      if self.args.success_pattern in line:
        success.set()

    returncode = self.ui.PipeProcessOutputToUI(
        [self.args.tpm_selftest] + self.args.tpm_args, callback=_Callback)

    self.assertTrue(
        success.is_set(),
        'TPM self-diagnose failed: Cannot find a success pattern: "%s". '
        'tpm_selftest returncode: %d.' % (self.args.success_pattern,
                                          returncode))
