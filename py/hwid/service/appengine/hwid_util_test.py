#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""AppEngine integration test for hwid_util"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_util


EXAMPLE_MEMORY_STRING = 'hynix_2gb_dimm0'


class HwidUtilTest(unittest.TestCase):

  def testGetSkuFromBom(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'dram': [EXAMPLE_MEMORY_STRING, EXAMPLE_MEMORY_STRING],
        'cpu': 'longstringwithcpu'
    })
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
        'dram': [EXAMPLE_MEMORY_STRING, EXAMPLE_MEMORY_STRING],
        'cpu': 'longstringwithcpu'
    })
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
