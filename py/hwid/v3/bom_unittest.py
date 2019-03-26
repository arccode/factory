#!/usr/bin/env python
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM


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


if __name__ == '__main__':
  unittest.main()
