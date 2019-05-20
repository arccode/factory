#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import configless_fields
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import probe


_TEST_DATABASE_PATH = os.path.join(
    os.path.dirname(__file__), 'testdata', 'TEST_CONFIGLESS_FIELD')

_TEST_PROBED_RESULTS_PATH = os.path.join(
    os.path.dirname(__file__), 'testdata',
    'TEST_CONFIGLESS_FIELD_probed_results')

_CF = configless_fields.ConfiglessFields


class ConfiglessFieldsTest(unittest.TestCase):
  def setUp(self):
    self.database = database.Database.LoadFile(
        _TEST_DATABASE_PATH, verify_checksum=False)
    self.probed_results = hwid_utils.GetProbedResults(
        infile=_TEST_PROBED_RESULTS_PATH)

  def testEncode(self):
    device_info = {
        'component': {
            'has_touchscreen': True
        }
    }
    vpd = {}
    bom = probe.GenerateBOMFromProbedResults(
        self.database,
        self.probed_results,
        device_info,
        vpd,
        common.OPERATION_MODE.normal,
        False,
        False)[0]
    # 0-8-3A-180's feature list field will be different if we extend new feature
    # to the end of version 0, see configless_fields.py for details
    self.assertEqual(_CF.Encode(self.database, bom, device_info, 0, False),
                     '0-8-3A-180')
    # Same as above, but with RMA mode.
    self.assertEqual(_CF.Encode(self.database, bom, device_info, 0, True),
                     '0-8-3A-181')

  def testDecode(self):
    # If we extend version 0, the decoded dict should be same.
    self.assertEqual(
        _CF.Decode('0-8-3A-180'),
        {
            'version': 0,
            'memory': 8,
            'storage': 58,
            'feature_list': {
                'has_touchscreen': 1,
                'has_touchpad': 0,
                'has_stylus': 0,
                'has_front_camera': 0,
                'has_rear_camera': 0,
                'has_fingerprint': 0,
                'is_convertible': 0,
                'is_rma_device': 0
            }
        })


if __name__ == '__main__':
  unittest.main()
