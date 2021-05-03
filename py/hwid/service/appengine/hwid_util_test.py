#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""AppEngine integration test for hwid_util"""

import os.path
import unittest

from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.v3 import database


EXAMPLE_MEMORY_STR = ['hynix_2gb_dimm0', 'hynix_0gb_dimm1']
SKU_TEST_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata', 'v3-sku.yaml')

EXAMPLE_MEMORY_COMPONENT1 = hwid_manager.Component(
    cls_='dram', name='dram_micron_1g_dimm2', fields={'size': '1024'})
EXAMPLE_MEMORY_COMPONENT2 = hwid_manager.Component(
    cls_='dram', name='hynix_2gb_dimm0', fields={'size': '2048'})
EXAMPLE_MEMORY_COMPONENT3 = hwid_manager.Component(
    cls_='dram', name='dram_hynix_512m_dimm2', fields={'size': '512'})

EXAMPLE_MEMORY_COMPONENTS = [
    EXAMPLE_MEMORY_COMPONENT1, EXAMPLE_MEMORY_COMPONENT2,
    EXAMPLE_MEMORY_COMPONENT3
]

EXAMPLE_MEMORY_COMPONENT_WITH_SIZE = hwid_manager.Component(
    cls_='dram', name='simple_tag', fields={'size': '1024'})
INVALID_MEMORY_COMPONENT = hwid_manager.Component(
    cls_='dram', name='no_size_in_fields_is_invalid_2GB')


class HwidUtilTest(unittest.TestCase):

  def setUp(self):
    self._comp_db = database.Database.LoadFile(SKU_TEST_FILE,
                                               verify_checksum=False)

  def testGetSkuFromBom(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents(
        {
            'dram': EXAMPLE_MEMORY_STR,
            'cpu': 'longstringwithcpu'
        }, comp_db=self._comp_db, verbose=True)
    bom.project = 'testprojectname'

    sku = hwid_util.GetSkuFromBom(bom)

    self.assertEqual('testprojectname_longstringwithcpu_4GB', sku['sku'])
    self.assertEqual('testprojectname', sku['project'])
    self.assertEqual('longstringwithcpu', sku['cpu'])
    self.assertEqual('4GB', sku['memory_str'])
    self.assertEqual(4294967296, sku['total_bytes'])

  def testGetSkuFromBomWithConfigless(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents(
        {
            'dram': EXAMPLE_MEMORY_STR,
            'cpu': 'longstringwithcpu'
        }, comp_db=self._comp_db, verbose=True)
    bom.project = 'testprojectname'

    configless = {'memory' : 8}
    sku = hwid_util.GetSkuFromBom(bom, configless)

    self.assertEqual('testprojectname_longstringwithcpu_8GB', sku['sku'])
    self.assertEqual('testprojectname', sku['project'])
    self.assertEqual('longstringwithcpu', sku['cpu'])
    self.assertEqual('8GB', sku['memory_str'])
    self.assertEqual(8589934592, sku['total_bytes'])

  def testGetComponentValueFromBom(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'bar': 'baz', 'null': []})

    value = hwid_util.GetComponentValueFromBom(bom, 'bar')
    self.assertEqual(['baz'], value)

    value = hwid_util.GetComponentValueFromBom(bom, 'null')
    self.assertEqual(None, value)

    value = hwid_util.GetComponentValueFromBom(bom, 'not_there')
    self.assertEqual(None, value)


class HwidUtilDramSizeTest(unittest.TestCase):

  def testAllMemoryTypes(self):
    result_str, total_bytes = hwid_util.GetTotalRamFromHwidData(
        EXAMPLE_MEMORY_COMPONENTS)
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
