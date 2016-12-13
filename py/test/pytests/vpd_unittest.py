#!/usr/bin/python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import mox
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device.boards import chromeos
from cros.factory.device.vpd import Partition
from cros.factory.test.factory import FactoryTestFailure
from cros.factory.test.factory_task import FactoryTask
from cros.factory.test.pytests import vpd
from cros.factory.test import shopfloor
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.type_utils import LazyProperty
from cros.factory.utils.type_utils import Obj

# Legacy unique/group codes for testing.
LEGACY_UNIQUE_CODE = ('323232323232323232323232323232323232'
                      '323232323232323232323232323256850612')
LEGACY_GROUP_CODE = ('333333333333333333333333333333333333'
                     '33333333333333333333333333332dbecc73')


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


class WriteVPDTaskTest(unittest.TestCase):

  def setUp(self):
    self.test_case = vpd.VPDTest()
    self.test_case.vpd = dict(ro={}, rw={})
    self.write_vpd_task = vpd.WriteVPDTask(self.test_case)
    self.mox = mox.Mox()
    self.test_case.dut = chromeos.ChromeOSBoard()
    self.vpd_ro = self.mox.CreateMock(Partition)
    self.vpd_rw = self.mox.CreateMock(Partition)
    LazyProperty.Override(self.test_case.dut.vpd, 'ro', self.vpd_ro)
    LazyProperty.Override(self.test_case.dut.vpd, 'rw', self.vpd_rw)

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testGoodLegacyUserGroupCode(self):
    self.test_case.registration_code_map = dict(user=LEGACY_UNIQUE_CODE,
                                                group=LEGACY_GROUP_CODE)
    # Stub out self.test.template.SetState().
    self.test_case.template = self.mox.CreateMock(OneSection)
    self.mox.StubOutWithMock(self.test_case.template, 'SetState')
    self.test_case.template.SetState(mox.IsA(unicode)).AndReturn(0)
    self.test_case.template.SetState(mox.IsA(str), append=True).AndReturn(0)
    # Stub out BuildBoard().short_name. Actually this is not required for
    # legacy code, we just use 'x86-generic' to pass the unit test.
    src = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src')
    default_board_path = os.path.join(src, 'scripts', '.default_board')
    with open(default_board_path, 'w') as f:
      f.write('x86-generic')

    # Stub out vpd.Update()
    self.vpd_ro.Update({}).AndReturn(0)
    self.vpd_rw.Update({}).AndReturn(0)
    self.vpd_rw.Update({'ubind_attribute': LEGACY_UNIQUE_CODE,
                        'gbind_attribute': LEGACY_GROUP_CODE}).AndReturn(0)

    # Stub out self.Pass().
    self.mox.StubOutWithMock(FactoryTask, 'Pass')
    FactoryTask.Pass().AndReturn(0)  # pylint: disable=E1120

    self.mox.ReplayAll()
    self.write_vpd_task.Run()

  def testTheSameLegacyUserGroupCodeFailure(self):
    self.test_case.registration_code_map = dict(user=LEGACY_UNIQUE_CODE,
                                                group=LEGACY_UNIQUE_CODE)
    # Stub out self.test.template.SetState().
    self.test_case.template = self.mox.CreateMock(OneSection)
    self.mox.StubOutWithMock(self.test_case.template, 'SetState')
    self.test_case.template.SetState(mox.IsA(unicode)).AndReturn(0)
    self.test_case.template.SetState(mox.IsA(str), append=True).AndReturn(0)

    # Stub out vpd.Update()
    self.vpd_ro.Update({}).AndReturn(0)
    self.vpd_rw.Update({}).AndReturn(0)

    self.mox.ReplayAll()
    self.assertRaisesRegexp(FactoryTestFailure,
                            '^user code and group code should not be the same$',
                            self.write_vpd_task.Run)


if __name__ == '__main__':
  unittest.main()
