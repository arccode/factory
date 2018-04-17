#!/usr/bin/env python
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

ALL_MEMORY_EXAMPLES = [
    EXAMPLE_MEMORY_STRING1, EXAMPLE_MEMORY_STRING2, EXAMPLE_MEMORY_STRING3,
    EXAMPLE_MEMORY_STRING4, EXAMPLE_MEMORY_STRING5, EXAMPLE_MEMORY_STRING6
]


class HwidUtilTest(unittest.TestCase):

  def testAllMemoryTypes(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        ALL_MEMORY_EXAMPLES)
    self.assertEqual('24064Mb', result_str)
    self.assertEqual(25232932864, total_bytes)

  def testMemoryType1(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING1])
    self.assertEqual('1Gb', result_str)
    self.assertEqual(1073741824, total_bytes)

  def testMemoryType2(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING2])
    self.assertEqual('2Gb', result_str)
    self.assertEqual(2147483648, total_bytes)

  def testMemoryType3(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING3])
    self.assertEqual('512Mb', result_str)
    self.assertEqual(536870912, total_bytes)

  def testMemoryType4(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING4])
    self.assertEqual('4Gb', result_str)
    self.assertEqual(4294967296, total_bytes)

  def testMemoryType5(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING5])
    self.assertEqual('8Gb', result_str)
    self.assertEqual(8589934592, total_bytes)

  def testMemoryType6(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_STRING5])
    self.assertEqual('8Gb', result_str)
    self.assertEqual(8589934592, total_bytes)

  def testEmptyList(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData([])
    self.assertEqual('0b', result_str)
    self.assertEqual(0, total_bytes)

  def testMemoryUnkown(self):
    self.assertRaises(hwid_util.HWIDUtilException,
                      hwid_util.GetTotalRamFromHwidData, ['Unknown'])


if __name__ == '__main__':
  unittest.main()