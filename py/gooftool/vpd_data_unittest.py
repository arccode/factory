#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool.vpd_data import FilterVPD, REDACTED


class FilterVPDTest(unittest.TestCase):
  def runTest(self):
    self.assertEquals(
        dict(a='A', b='B', ubind_attribute=REDACTED, gbind_attribute=REDACTED),
        FilterVPD(
            dict(a='A', b='B', ubind_attribute='U', gbind_attribute='G')))


if __name__ == '__main__':
  unittest.main()
