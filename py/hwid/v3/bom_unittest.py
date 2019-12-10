#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import random
import unittest

from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3.bom import RamSize


class BOMTest(unittest.TestCase):
  def testSetComponent(self):
    bom = BOM(None, None, {})

    bom.SetComponent('comp_cls_1', 'comp_1_1')
    bom.SetComponent('comp_cls_2', ['comp_2_1', 'comp_2_2'])

    self.assertEqual(
        bom.components,
        {
            'comp_cls_1': ['comp_1_1'],
            'comp_cls_2': ['comp_2_1', 'comp_2_2'],
        })

    bom.SetComponent('comp_cls_2', ['comp_2_2', 'comp_2_1'])
    self.assertEqual(
        bom.components,
        {
            'comp_cls_1': ['comp_1_1'],
            # components should be sorted.
            'comp_cls_2': ['comp_2_1', 'comp_2_2'],
        })


_MEMORY_EXAMPLES = [
    ('dram_micron_1g_dimm2', 1 << 30, '1GB'),
    ('hynix_2gb_dimm0', 2 << 30, '2GB'),
    ('dram_hynix_512m_dimm2', 512 << 20, '512MB'),
    ('2x2GB_DDR3_1600', 4 << 30, '4GB'),
    ('K4EBE304EB_EGCF_8gb', 8 << 30, '8GB'),
    ('K4EBE304EB_EGCF_8gb_', 8 << 30, '8GB'),
    ('H9HCNNN8KUMLHR_1gb_slot2', 1 << 30, '1GB'),
    ('Samsung_4G_M471A5644EB0-CRC_2048mb_1', 2048 << 20, '2GB'),
    ('some_strange_size_10000000KB', 10000000 << 10, '10000000KB'),
    ('some_strange_size_1048576KB', 1048576 << 10, '1GB'),
]

_MEMORY_BAD_EXAMPLES = [
    'Samsung_4_M471A5644EB0-CRC_2048_1',
    'concat_letterand2048MB',
    '1024MBconcat_other',
]


class RamSizeTest(unittest.TestCase):
  def testInit(self):
    for ram_size_str, ram_bytes, result_str in _MEMORY_EXAMPLES:
      self.assertEqual(RamSize(ram_size_str=ram_size_str).byte_count, ram_bytes)
      self.assertEqual(RamSize(byte_count=ram_bytes).byte_count, ram_bytes)
      self.assertEqual(str(RamSize(ram_size_str=ram_size_str)), result_str)

  def testBadInit(self):
    for bad_ram_str in _MEMORY_BAD_EXAMPLES:
      with self.assertRaises(ValueError) as error:
        RamSize(ram_size_str=bad_ram_str)
      self.assertEqual('Invalid DRAM: %s' % bad_ram_str, str(error.exception))

  def testAdd(self):
    r1 = random.randint(0, 1 << 30)
    r2 = random.randint(0, 1 << 30)
    ram_size = RamSize(byte_count=r1) + RamSize(byte_count=r2)
    self.assertEqual(ram_size.byte_count, r1 + r2)

  def testMul(self):
    size = random.randint(0, 1 << 30)
    r = random.randint(0, 20)
    ram_size = RamSize(byte_count=size)
    self.assertEqual((ram_size * r).byte_count, r * size)
    self.assertEqual((r * ram_size).byte_count, r * size)


if __name__ == '__main__':
  unittest.main()
