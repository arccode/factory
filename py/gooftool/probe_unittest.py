#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.gooftool import probe
from cros.factory.system import vpd


class ProbeRegionUnittest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(vpd.ro, 'get')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testProbeVPD(self):
    vpd.ro.get('region').AndReturn('us')
    self.mox.ReplayAll()

    result = probe._ProbeRegion() # pylint: disable=W0212
    self.assertEquals(
        [{'region_code': 'us',
          'keyboards': 'xkb:us::eng',
          'time_zone': 'America/Los_Angeles',
          'language_codes': 'en-US',
          'keyboard_mechanical_layout': 'ANSI'}],
        result)

    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
