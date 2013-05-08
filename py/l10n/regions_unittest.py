#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.l10n import regions

# pylint: disable=W0212

class RegionTest(unittest.TestCase):
  def testNoDuplicateRegions(self):
    # Duplicate countries will have been removed when turning the list
    # into a dict.
    self.assertEquals(len(regions._REGIONS_LIST),
                      len(regions.REGIONS))


if __name__ == '__main__':
  unittest.main()
