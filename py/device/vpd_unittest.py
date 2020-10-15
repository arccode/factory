#!/usr/bin/env python3
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.device import device_utils


class VPDTest(unittest.TestCase):
  # pylint: disable=no-value-for-parameter

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.vpd = self.dut.vpd

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetValue')
  def testGet(self, get_value_mock, get_all_data_mock):
    def GetValueSideEffect(*args, **unused_kwargs):
      if args[0] == 'a':
        return 'aa'
      if args[0] == 'b':
        return 123
      return None

    get_all_data_mock.return_value = dict(a='b', foo='bar', empty='')
    get_value_mock.side_effect = GetValueSideEffect

    self.assertEqual(dict(a='b', foo='bar', empty=''), self.vpd.rw.GetAll())
    get_all_data_mock.assert_called_once_with(partition='RW_VPD')

    self.assertEqual('aa', self.vpd.ro.get('a'))
    get_value_mock.assert_called_with('a', default_value=None,
                                      partition='RO_VPD')

    self.assertEqual(123, self.vpd.ro.get('b', 123))
    get_value_mock.assert_called_with('b', default_value=123,
                                      partition='RO_VPD')

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  @mock.patch('cros.factory.gooftool.vpd.VPDTool.UpdateData')
  def testUpdate(self, update_data_mock, get_all_data_mock):
    get_all_data_mock.return_value = dict(a='b', foo='bar', empty='')

    self.vpd.rw.Update(dict(w='x', y='z', foo=None))
    get_all_data_mock.assert_called_once_with(partition='RW_VPD')
    update_data_mock.assert_called_once_with(dict(w='x', y='z', foo=None),
                                             partition='RW_VPD')

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  @mock.patch('cros.factory.gooftool.vpd.VPDTool.UpdateData')
  def testUpdatePartial(self, update_data_mock, get_all_data_mock):
    # "a"="b" is already in vpd, update will skip it.
    # "unset" is already not in vpd, update will skip it.
    get_all_data_mock.return_value = dict(a='b', foo='bar', empty='')

    self.vpd.rw.Update(dict(a='b', w='x', y='z', unset=None))
    get_all_data_mock.assert_called_once_with(partition='RW_VPD')
    update_data_mock.assert_called_once_with(dict(w='x', y='z'),
                                             partition='RW_VPD')

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.UpdateData')
  def testDeleteOne(self, update_data_mock):
    self.vpd.rw.Delete('a')
    update_data_mock.assert_called_once_with(dict(a=None), partition='RW_VPD')

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.UpdateData')
  def testDeleteTwo(self, update_data_mock):
    self.vpd.rw.Delete('a', 'b')
    update_data_mock.assert_called_once_with(dict(a=None, b=None),
                                             partition='RW_VPD')

  @mock.patch('cros.factory.gooftool.vpd.VPDTool.GetAllData')
  def testGetPartition(self, get_all_data_mock):
    get_all_data_mock.return_value = dict(foo='bar')
    self.assertEqual(dict(foo='bar'),
                     self.vpd.GetPartition('rw').GetAll())
    get_all_data_mock.assert_called_with(partition='RW_VPD')

    get_all_data_mock.return_value = dict(bar='foo')
    self.assertEqual(dict(bar='foo'),
                     self.vpd.GetPartition('ro').GetAll())
    get_all_data_mock.assert_called_with(partition='RO_VPD')

if __name__ == '__main__':
  unittest.main()
