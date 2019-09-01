#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import camera_cros


class CameraCrosTest(unittest.TestCase):
  def tearDown(self):
    camera_cros.CameraCrosFunction.CleanCachedData()

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              return_value=('            Name | Vendor ID\n'
                            '  xy12345 1-1111 | 11\n'
                            '  ab67890 2-2222 | 22\n'))
  def testNormal(self, unused_mock_check_output):
    func = camera_cros.CameraCrosFunction()
    results = func()
    expected = [{'name': 'xy12345 1-1111', 'vendor': '11'},
                {'name': 'ab67890 2-2222', 'vendor': '22'}]
    self.assertItemsEqual(results, expected)

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              return_value='            Name | Vendor ID\n')
  def testEmpty(self, unused_mock_check_output):
    func = camera_cros.CameraCrosFunction()
    self.assertEquals(func(), [])


if __name__ == '__main__':
  unittest.main()
