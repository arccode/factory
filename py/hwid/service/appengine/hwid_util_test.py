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


EXAMPLE_MEMORY = ['hynix_2gb_dimm0', 'hynix_0gb_dimm1']
SKU_TEST_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata', 'v3-sku.yaml')


class HwidUtilTest(unittest.TestCase):

  def setUp(self):
    self._comp_db = database.Database.LoadFile(SKU_TEST_FILE,
                                               verify_checksum=False)

  def testGetSkuFromBom(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'dram': EXAMPLE_MEMORY,
        'cpu': 'longstringwithcpu'
    }, comp_db=self._comp_db, verbose=True)
    bom.board = 'testboardname'

    sku = hwid_util.GetSkuFromBom(bom)

    self.assertEqual('testboardname_longstringwithcpu_4GB', sku['sku'])
    self.assertEqual('testboardname', sku['board'])
    self.assertEqual('longstringwithcpu', sku['cpu'])
    self.assertEqual('4GB', sku['memory_str'])
    self.assertEqual(4294967296, sku['total_bytes'])

  def testGetSkuFromBomWithConfigless(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'dram': EXAMPLE_MEMORY,
        'cpu': 'longstringwithcpu'
    }, comp_db=self._comp_db, verbose=True)
    bom.board = 'testboardname'

    configless = {'memory' : 8}
    sku = hwid_util.GetSkuFromBom(bom, configless)

    self.assertEqual('testboardname_longstringwithcpu_8GB', sku['sku'])
    self.assertEqual('testboardname', sku['board'])
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


if __name__ == '__main__':
  unittest.main()
