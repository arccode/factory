#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import device_data
from cros.factory.test import state


class ReadDeviceDataFromVPDUnittest(unittest.TestCase):
  def setUp(self):
    self.state_proxy = state.StubFactoryState()

  def testDeriveDeviceDataKey(self):
    rule = ('factory.device_data.*', '')

    expected = {
        'factory.device_data.a': 'a',
        'factory.device_data.a.b': 'a.b', }

    result = {
        # pylint: disable=protected-access
        key: device_data._DeriveDeviceDataKey(rule, key)
        for key in expected}

    self.assertDictEqual(expected, result)

  def testRunTest(self):
    device_data.state.GetInstance = (
        lambda *args, **kwargs: self.state_proxy)

    key_map = {
        'factory.device_data.*': '',
        'abc': 'ABC',
    }

    vpd_data = {
        'factory.device_data.a': 'TRUE',
        'factory.device_data.b.c': 'foo',
        'abc': '123',
        'def': '456',
    }

    device_data.UpdateDeviceDataFromVPD({'ro': key_map}, {'ro': vpd_data})

    self.assertDictEqual(
        {
            'a': True,
            'b': {'c': 'foo'},
            'ABC': '123',
        },
        device_data.GetAllDeviceData())


class VerifyDeviceDataUnittest(unittest.TestCase):
  def testComponentDomain(self):
    device_data.VerifyDeviceData(
        {
            'component.has_aabb': 0,
            'component.has_ccdd': True,
        })

    self.assertRaises(
        ValueError, device_data.VerifyDeviceData,
        {
            'component.has_eeff': 'Y'
        })


if __name__ == '__main__':
  unittest.main()
