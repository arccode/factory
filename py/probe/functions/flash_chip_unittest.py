#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import subprocess
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import flashchip


class FlashChipFunctionTest(unittest.TestCase):

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              return_value='vendor="Google" name="Chip"')
  def testNormal(self, MockCheckOutput):
    expected = {'vendor': 'Google', 'name': 'Chip'}
    results = flashchip.FlashChipFunction(chip='main')()
    self.assertEquals(results, [expected])
    MockCheckOutput.assert_called_with(
        ['flashrom', '-p', 'host', '--flash-name'])

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              side_effect=subprocess.CalledProcessError(1, 'command'))
  def testNoOutput(self, MockCheckOutput):
    results = flashchip.FlashChipFunction(chip='ec')()
    self.assertEquals(results, [])
    MockCheckOutput.assert_called_with(['flashrom', '-p', 'ec', '--flash-name'])


if __name__ == '__main__':
  unittest.main()
