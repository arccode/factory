#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unittest for cros.factory.utils.type_utils."""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import type_utils


class FlattenListTest(unittest.TestCase):
  def runTest(self):
    self.assertEquals([], type_utils.FlattenList([]))
    self.assertEquals([], type_utils.FlattenList([[]]))
    self.assertEquals([1], type_utils.FlattenList([1]))
    self.assertEquals([1], type_utils.FlattenList([1, []]))
    self.assertEquals([1, 2, 3, 4, 5, 6],
                      type_utils.FlattenList([1, 2, [3, 4, []], 5, 6]))

if __name__ == "__main__":
  unittest.main()
