#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import vpd


class VPDFunctionTest(unittest.TestCase):

  @mock.patch('cros.factory.utils.process_utils.CheckOutput', return_value='tw')
  def testSimpleCommand(self, MockCheckOutput):
    results = vpd.VPDFunction(field='region', key='region_code')()
    self.assertEquals(results, [{'region_code': 'tw'}])
    MockCheckOutput.assert_called_once_with(
        'vpd -i RO_VPD -g region', shell=True, log=True)

  @mock.patch('cros.factory.utils.process_utils.CheckOutput', return_value='')
  def testNoResult(self, MockCheckOutput):
    results = vpd.VPDFunction(field='FAKE', from_rw=True)()
    self.assertEquals(results, [])
    MockCheckOutput.assert_called_once_with(
        'vpd -i RW_VPD -g FAKE', shell=True, log=True)


if __name__ == '__main__':
  unittest.main()
