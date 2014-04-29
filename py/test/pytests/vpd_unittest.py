#!/usr/bin/python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.common import Obj
from cros.factory.test import shopfloor
from cros.factory.test.pytests import vpd


class VPDBrandingFieldsTest(unittest.TestCase):
  def setUp(self):
    self.test_case = vpd.VPDTest()
    self.test_case.vpd = dict(ro={})
    self.device_data = {}
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(shopfloor, 'GetDeviceData')

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testFixed(self):
    self.test_case.args = Obj(rlz_brand_code='ABCD', customization_id='FOO')
    self.mox.ReplayAll()
    self.test_case.ReadBrandingFields()
    self.assertEquals(dict(rlz_brand_code='ABCD', customization_id='FOO'),
                      self.test_case.vpd['ro'])

  def testBrandCodeOnly(self):
    self.test_case.args = Obj(rlz_brand_code='ABCD', customization_id=None)
    self.mox.ReplayAll()
    self.test_case.ReadBrandingFields()
    self.assertEquals(dict(rlz_brand_code='ABCD'), self.test_case.vpd['ro'])

  def testConfigurationIdOnly(self):
    self.test_case.args = Obj(rlz_brand_code=None, customization_id='FOO')
    self.mox.ReplayAll()
    self.test_case.ReadBrandingFields()
    self.assertEquals(dict(customization_id='FOO'), self.test_case.vpd['ro'])

  def testFromShopFloor(self):
    self.test_case.args = Obj(rlz_brand_code=vpd.FROM_DEVICE_DATA,
                              customization_id=vpd.FROM_DEVICE_DATA)
    shopfloor.GetDeviceData().AndReturn(dict(rlz_brand_code='ABCD',
                                             customization_id='FOO-BAR'))
    self.mox.ReplayAll()
    self.test_case.ReadBrandingFields()
    self.assertEquals(dict(rlz_brand_code='ABCD', customization_id='FOO-BAR'),
                      self.test_case.vpd['ro'])

  def testBadBrandCode(self):
    self.test_case.args = Obj(rlz_brand_code='ABCDx')
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Bad format for rlz_brand_code',
                            self.test_case.ReadBrandingFields)

  def testBadConfigurationId(self):
    self.test_case.args = Obj(rlz_brand_code=None, customization_id='FOO-BARx')
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Bad format for customization_id',
                            self.test_case.ReadBrandingFields)



if __name__ == '__main__':
  unittest.main()
