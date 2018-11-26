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
    self.assertEqual(_CF.Encode(self.database, bom, device_info, 0),
                     '0-8-3A-01')

  def testDecode(self):
    self.assertEqual(
        _CF.Decode('0-8-3A-00'),
        {
            'version': 0,
            'memory': 8,
            'storage': 58,
            'feature_list': {
                'has_touchscreen': 0,
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
