# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs tpm_selftest to perform TPM self-diagnosis."""

import logging
import os
import subprocess
import threading
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import Escape, MakeLabel, UI
from cros.factory.test.ui_templates import OneScrollableSection
from cros.factory.utils.process_utils import Spawn

_TEST_TITLE = MakeLabel('TPM Self-diagnosis', u'TPM 自我诊断')
_CSS = '#state {text-align:left;}'


class TpmDiagnosisTest(unittest.TestCase):
  ARGS = [
    Arg('tpm_selftest', str, 'Path of tpm_selftest program.',
        default='/usr/local/sbin/tpm_selftest'),
    Arg('tpm_args', list, 'List of tpm_selftest args.',
        default=['-l', 'debug']),
    Arg('success_pattern', str, 'Pattern of success.',
        default='tpm_selftest succeeded')
  ]

  def setUp(self):
    self.assertTrue(os.path.isfile(self.args.tpm_selftest),
                    msg='%s is missing.' % self.args.tpm_selftest)
    self._ui = UI()
    self._template = OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def DiagnoseTpm(self):
    """Runs tpm_selftest.

    It shows diagnosis result on factory UI.
    """
    p = Spawn([self.args.tpm_selftest] + self.args.tpm_args,
              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, log=True)
    success = False
    for line in iter(p.stdout.readline, ''):
      logging.info(line.strip())
      self._template.SetState(Escape(line), append=True)
      if line.find(self.args.success_pattern) != -1:
        success = True

    p.poll()
    if success:
      self._ui.Pass()
    else:
      self._ui.Fail(
        'TPM self-diagnose failed: Cannot find a success pattern: "%s". '
        'tpm_selftest returncode: %d.' % (self.args.success_pattern,
                                          p.returncode))

  def runTest(self):
    threading.Thread(target=self.DiagnoseTpm).start()
    self._ui.Run()
