#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests hwid_util"""

import unittest

from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database


EMPTY_COMPONENT_INFO = database.ComponentInfo(
    values={}, status=common.COMPONENT_STATUS.supported)

EXAMPLE_MEMORY_COMPONENT1 = hwid_manager.Component(
    cls_='dram', name='dram_micron_1g_dimm2', fields={'size': '1024'})
EXAMPLE_MEMORY_COMPONENT2 = hwid_manager.Component(
    cls_='dram', name='hynix_2gb_dimm0', fields={'size': '2048'})
EXAMPLE_MEMORY_COMPONENT3 = hwid_manager.Component(
    cls_='dram', name='dram_hynix_512m_dimm2', fields={'size': '512'})

MEMORY_EXAMPLES = [
    EXAMPLE_MEMORY_COMPONENT1, EXAMPLE_MEMORY_COMPONENT2,
    EXAMPLE_MEMORY_COMPONENT3
]

EXAMPLE_MEMORY_COMPONENT_WITH_SIZE = hwid_manager.Component(
    cls_='dram', name='simple_tag', fields={'size': '1024'})
INVALID_MEMORY_COMPONENT = hwid_manager.Component(
    cls_='dram', name='no_size_in_fields_is_invalid_2GB')


class HwidUtilTest(unittest.TestCase):

  def testAllMemoryTypes(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(MEMORY_EXAMPLES)
    self.assertEqual('3584MB', result_str)
    self.assertEqual(3758096384, total_bytes)

  def testMemoryType1(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_COMPONENT1])
    self.assertEqual('1GB', result_str)
    self.assertEqual(1073741824, total_bytes)

  def testMemoryType2(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_COMPONENT2])
    self.assertEqual('2GB', result_str)
    self.assertEqual(2147483648, total_bytes)

  def testEmptyList(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData([])
    self.assertEqual('0B', result_str)
    self.assertEqual(0, total_bytes)

  def testMemoryFromSizeField(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        [EXAMPLE_MEMORY_COMPONENT_WITH_SIZE])
    self.assertEqual('1GB', result_str)
    self.assertEqual(1073741824, total_bytes)

  def testMemoryOnlySizeInName(self):
    self.assertRaises(hwid_util.HWIDUtilException,
                      hwid_util.GetTotalRamFromHwidData,
                      [INVALID_MEMORY_COMPONENT])


if __name__ == '__main__':
  unittest.main()
