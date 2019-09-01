#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import vpd


class VPDFunctionTest(unittest.TestCase):

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  def testSimpleCommand(self, get_all_data_func):
    get_all_data_func.return_value = {'region': 'tw', 'aa': 'bb'}
    vpd.VPDFunction.CleanCachedData()
    vpd_function = vpd.VPDFunction()
    self.assertEquals(vpd_function(), [{'region': 'tw', 'aa': 'bb'}])

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  def testChangeKey(self, get_all_data_func):
    get_all_data_func.return_value = {'region': 'tw'}
    vpd.VPDFunction.CleanCachedData()
    vpd_function = vpd.VPDFunction(fields=['region'], key='region_code')
    self.assertEquals(vpd_function(), [{'region_code': 'tw'}])

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  def testListOfFieldsCommand(self, get_all_data_func):
    get_all_data_func.return_value = {'region': 'tw', 'sn': 'xxx'}
    vpd.VPDFunction.CleanCachedData()
    vpd_function = vpd.VPDFunction(fields=['region', 'sn'])
    self.assertEquals(vpd_function(), [{'region': 'tw', 'sn': 'xxx'}])

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  def testNoResult(self, get_all_data_func):
    get_all_data_func.return_value = {'region': 'tw'}
    vpd.VPDFunction.CleanCachedData()
    vpd_function = vpd.VPDFunction(fields=['FAKE1', 'region'])
    self.assertEquals(vpd_function(), [])


if __name__ == '__main__':
  unittest.main()
