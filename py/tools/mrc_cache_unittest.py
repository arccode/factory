#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for mrc_cache."""

import unittest

import mock

from cros.factory.tools import mrc_cache


class MRCCacheTest(unittest.TestCase):

  def setUp(self):
    self.dut = mock.MagicMock()

  @mock.patch('cros.factory.tools.mrc_cache.GetMRCSections')
  def testEraseTrainingDataForX86(self, get_mrc_section_mock):
    get_mrc_section_mock.return_value = ['RECOVERY_MRC_CACHE', 'RW_MRC_CACHE']
    self.dut.CheckOutput.return_value = mrc_cache.ARCH.x86

    mrc_cache.EraseTrainingData(self.dut)

    check_call_calls = [
        mock.call([
            'flashrom', '-p', 'host', '-E', '-i', 'RECOVERY_MRC_CACHE', '-i',
            'RW_MRC_CACHE'
        ],
                  log=True),
        mock.call('crossystem recovery_request=0xC4', log=True)
    ]
    self.assertEqual(self.dut.CheckCall.call_args_list, check_call_calls)

  @mock.patch('cros.factory.tools.mrc_cache.GetMRCSections')
  def testEraseTrainingDataForArm(self, get_mrc_section_mock):
    get_mrc_section_mock.return_value = ['RW_DDR_TRAINING', 'RO_DDR_TRAINING']
    self.dut.CheckOutput.return_value = mrc_cache.ARCH.arm

    mrc_cache.EraseTrainingData(self.dut)
    print(self.dut.CheckCall.call_args_list)

    check_call_calls = [
        mock.call([
            'flashrom', '-p', 'host', '-E', '-i', 'RW_DDR_TRAINING', '-i',
            'RO_DDR_TRAINING'
        ],
                  log=True)
    ]
    self.assertEqual(self.dut.CheckCall.call_args_list, check_call_calls)

  @mock.patch('cros.factory.tools.mrc_cache.GetMRCSections')
  def testVerifyTrainingDataForX86(self, get_mrc_section_mock):
    get_mrc_section_mock.return_value = ['RECOVERY_MRC_CACHE', 'RW_MRC_CACHE']
    self.dut.CheckOutput.return_value = mrc_cache.ARCH.x86
    temp_file = '/tmp_file'
    self.dut.temp.TempFile.return_value.__enter__.return_value = temp_file

    mrc_cache.VerifyTrainingData(self.dut)

    check_call_calls = [
        mock.call(
            'flashrom -p host -r /dev/null -i RECOVERY_MRC_CACHE:%s' %
            temp_file,
            log=True),
        mock.call('futility validate_rec_mrc %s' % temp_file, log=True),
        mock.call(
            'flashrom -p host -r /dev/null -i RW_MRC_CACHE:%s' % temp_file,
            log=True),
        mock.call('futility validate_rec_mrc %s' % temp_file, log=True)
    ]
    self.assertEqual(self.dut.CheckCall.call_args_list, check_call_calls)

  def testVerifyTrainingDataForArm(self):
    self.dut.CheckOutput.return_value = mrc_cache.ARCH.arm

    mrc_cache.VerifyTrainingData(self.dut)

    self.assertEqual(self.dut.CheckCall.call_args_list, [])


if __name__ == '__main__':
  unittest.main()
