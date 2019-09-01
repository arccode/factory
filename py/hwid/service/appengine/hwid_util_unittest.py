#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests hwid_util"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import hwid_util

EXAMPLE_MEMORY_STRING1 = 'dram_micron_1g_dimm2'
EXAMPLE_MEMORY_STRING2 = 'hynix_2gb_dimm0'
EXAMPLE_MEMORY_STRING3 = 'dram_hynix_512m_dimm2'
EXAMPLE_MEMORY_STRING4 = '2x2GB_DDR3_1600'
EXAMPLE_MEMORY_STRING5 = 'K4EBE304EB_EGCF_8gb'
EXAMPLE_MEMORY_STRING6 = 'K4EBE304EB_EGCF_8gb_'
EXAMPLE_MEMORY_STRING7 = 'H9HCNNN8KUMLHR_1gb_slot2'
EXAMPLE_MEMORY_STRING8 = 'Samsung_4G_M471A5644EB0-CRC_2048mb_1'

MEMORY_EXAMPLES = [
    EXAMPLE_MEMORY_STRING1, EXAMPLE_MEMORY_STRING2, EXAMPLE_MEMORY_STRING3,
    EXAMPLE_MEMORY_STRING4, EXAMPLE_MEMORY_STRING5, EXAMPLE_MEMORY_STRING6
]


class HwidUtilTest(unittest.TestCase):

  def testAllMemoryTypes(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(MEMORY_EXAMPLES)
    self.assertEqual('24064MB', result_str)
    self.assertEqual(25232932864, total_bytes)

  def testMemoryType1(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING1])
    self.assertEqual('1GB', result_str)
    self.assertEqual(1073741824, total_bytes)

  def testMemoryType2(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING2])
    self.assertEqual('2GB', result_str)
    self.assertEqual(2147483648, total_bytes)

  def testMemoryType3(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING3])
    self.assertEqual('512MB', result_str)
    self.assertEqual(536870912, total_bytes)

  def testMemoryType4(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING4])
    self.assertEqual('4GB', result_str)
    self.assertEqual(4294967296, total_bytes)

  def testMemoryType5(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING5])
    self.assertEqual('8GB', result_str)
    self.assertEqual(8589934592, total_bytes)

  def testMemoryType6(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING5])
    self.assertEqual('8GB', result_str)
    self.assertEqual(8589934592, total_bytes)

  def testMemoryType7(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING7])
    self.assertEqual('1GB', result_str)
    self.assertEqual(1073741824, total_bytes)

  def testMemoryType8(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING8])
    self.assertEqual('2GB', result_str)
    self.assertEqual(2147483648, total_bytes)

  def testEmptyList(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData([])
    self.assertEqual('0B', result_str)
    self.assertEqual(0, total_bytes)

  def testMemoryUnkown(self):
    self.assertRaises(hwid_util.HWIDUtilException,
                      hwid_util.GetTotalRamFromHwidData, ['Unknown'])


if __name__ == '__main__':
  unittest.main()
