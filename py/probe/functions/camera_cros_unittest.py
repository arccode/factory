#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

from cros.factory.probe.functions import camera_cros


class CameraCrosTest(unittest.TestCase):
  def tearDown(self):
    camera_cros.CameraCrosFunction.CleanCachedData()

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              return_value=('[ {\n'
                            '  "name": "xy12345 1-1111",\n'
                            '  "vendor": "11"\n'
                            '}, {\n'
                            '  "name": "ab67890 2-2222",\n'
                            '  "module_id": "AB0001",\n'
                            '  "sensor_id": "CD0002"\n'
                            '} ]\n'))
  def testNormal(self, unused_mock_check_output):
    func = camera_cros.CameraCrosFunction()
    results = func()
    expected = [{
        'name': 'xy12345 1-1111',
        'vendor': '11',
        'type': 'webcam'
    }, {
        'name': 'ab67890 2-2222',
        'module_id': 'AB0001',
        'sensor_id': 'CD0002',
        'type': 'webcam'
    }]
    self.assertCountEqual(results, expected)

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              return_value='[  ]\n')
  def testEmpty(self, unused_mock_check_output):
    func = camera_cros.CameraCrosFunction()
    self.assertEqual(func(), [])


if __name__ == '__main__':
  unittest.main()
