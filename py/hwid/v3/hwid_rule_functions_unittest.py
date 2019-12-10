#!/usr/bin/env python3
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3.hwid_rule_functions import ComponentEq
from cros.factory.hwid.v3.hwid_rule_functions import ComponentIn
from cros.factory.hwid.v3.hwid_rule_functions import GetDeviceInfo
from cros.factory.hwid.v3.hwid_rule_functions import GetImageId
from cros.factory.hwid.v3.hwid_rule_functions import GetOperationMode
from cros.factory.hwid.v3.hwid_rule_functions import GetPhase
from cros.factory.hwid.v3.hwid_rule_functions import GetVPDValue
from cros.factory.hwid.v3.hwid_rule_functions import SetComponent
from cros.factory.hwid.v3.hwid_rule_functions import SetImageId
from cros.factory.hwid.v3.rule import Context
from cros.factory.hwid.v3.rule import SetContext
from cros.factory.test.rules import phase


_TEST_DATABASE_PATH = os.path.join(
    os.path.dirname(__file__), 'testdata', 'test_hwid_rule_functions_db.yaml')


class HWIDRuleTest(unittest.TestCase):

  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH,
                                      verify_checksum=False)
    self.bom = BOM(
        encoding_pattern_index=0, image_id=0, components={'cpu': ['cpu_0']})
    self.device_info = {'SKU': 1, 'has_cellular': False}
    self.vpd = {
        'ro': {
            'serial_number': 'foo',
            'region': 'us'
        },
        'rw': {
            'registration_code': 'buz'
        }
    }
    self.context = Context(
        database=self.database, bom=self.bom,
        mode=common.OPERATION_MODE.normal,
        device_info=self.device_info, vpd=self.vpd)

    SetContext(self.context)

  def testComponentEq(self):
    self.assertTrue(ComponentEq('cpu', 'cpu_0'))
    self.assertFalse(ComponentEq('cpu', 'cpu_3'))

  def testComponentIn(self):
    self.assertTrue(ComponentIn('cpu', ['cpu_0', 'cpu_1', 'cpu_2']))
    self.assertFalse(ComponentIn('cpu', ['cpu_1', 'cpu_2']))

  def testSetComponent(self):
    SetComponent('cpu', 'cpu_3')
    self.assertEqual(['cpu_3'], self.bom.components['cpu'])

    SetComponent('cpu', None)
    self.assertEqual(0, len(self.bom.components['cpu']))

  def testGetSetImageId(self):
    self.assertEqual(0, GetImageId())

    SetImageId(1)
    self.assertEqual(1, self.bom.image_id)
    self.assertEqual(1, GetImageId())

    SetImageId(2)
    self.assertEqual(2, self.bom.image_id)
    self.assertEqual(2, GetImageId())

  def testGetOperationMode(self):
    self.assertEqual(common.OPERATION_MODE.normal, GetOperationMode())

  def testGetDeviceInfo(self):
    self.assertEqual(1, GetDeviceInfo('SKU'))
    self.assertEqual(False, GetDeviceInfo('has_cellular'))

    self.assertEqual(1, GetDeviceInfo('SKU'))
    self.assertEqual('Default', GetDeviceInfo('has_something', 'Default'))

  def testGetVPDValue(self):
    self.assertEqual('foo', GetVPDValue('ro', 'serial_number'))
    self.assertEqual('buz', GetVPDValue('rw', 'registration_code'))

  def testGetPhase(self):
    # Should be 'PVT' when no build phase is set.
    self.assertEqual('PVT', GetPhase())

    phase._current_phase = phase.PROTO  # pylint: disable=protected-access
    self.assertEqual('PROTO', GetPhase())

    phase._current_phase = phase.PVT_DOGFOOD  # pylint: disable=protected-access
    self.assertEqual('PVT_DOGFOOD', GetPhase())


if __name__ == '__main__':
  unittest.main()
