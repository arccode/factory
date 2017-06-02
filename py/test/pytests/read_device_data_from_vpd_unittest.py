#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.pytests import read_device_data_from_vpd as pytest
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
        key: pytest.ReadDeviceDataFromVPD._DeriveDeviceDataKey(rule, key)
        for key in expected}

    self.assertDictEqual(expected, result)

  def testRunTest(self):
    pytest.state.get_instance = lambda *args, **kwargs: self.state_proxy

    def WrapUpdateDeviceData(func):
      def NewUpdateDeviceData(new_device_data):
        return func(new_device_data, post_update_event=False)
      return NewUpdateDeviceData

    pytest.state.UpdateDeviceData = WrapUpdateDeviceData(
        pytest.state.UpdateDeviceData)

    test_instance = pytest.ReadDeviceDataFromVPD()

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

    test_instance.UpdateDeviceData(key_map, vpd_data)

    self.assertDictEqual(
        {
            'a': True,
            'b': {'c': 'foo'},
            'ABC': '123',
        },
        pytest.state.GetAllDeviceData())


if __name__ == '__main__':
  unittest.main()
