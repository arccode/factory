#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies that the write-protect switch is on."""

import logging
import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg


class WriteProtectSwitchTest(unittest.TestCase):
  ARGS = [
      Arg('has_ectool', bool, 'Has ectool utility or not.', default=True)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    self.assertEqual(1, int(self.dut.CheckOutput(['crossystem', 'wpsw_cur'],
                                                 log=True).strip()))

    if self.args.has_ectool:
      ectool_flashprotect = self.dut.CheckOutput(
          ['ectool', 'flashprotect'], log=True)

      logging.info('ectool flashprotect:\n%s', ectool_flashprotect)
      # Multiline is important: we need to see wp_gpio_asserted on
      # the same line.
      self.assertTrue(re.search('^Flash protect flags:.+wp_gpio_asserted',
                                ectool_flashprotect, re.MULTILINE),
                      'ectool flashprotect is missing wp_gpio_asserted')
