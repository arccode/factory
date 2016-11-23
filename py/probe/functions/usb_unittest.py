#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import usb


class USBFunctionTest(unittest.TestCase):
  def setUp(self):
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def _WriteValue(self, path, expected_value):
    for key in expected_value:
      with open(os.path.join(path, key), 'w') as f:
        f.write(expected_value[key])

  def testNormal(self):
    # Only required fields.
    expected_value = {
        'idVendor': 'google',
        'idProduct': 'chromebook'}
    self._WriteValue(self.tmp_dir, expected_value)

    func = usb.USBFunction(dir_path=self.tmp_dir)
    result = func()
    self.assertEquals(result, [expected_value])

  def testAllOptionalField(self):
    # Required and all optional fields.
    expected_value = {
        'idVendor': 'google',
        'idProduct': 'chromebook',
        'manufacturer': 'Google',
        'product': 'Chromebook',
        'bcdDevice': 'foo'}
    self._WriteValue(self.tmp_dir, expected_value)

    func = usb.USBFunction(dir_path=self.tmp_dir)
    result = func()
    self.assertEquals(result, [expected_value])

  def testPartialOptionalField(self):
    # Required and partial optional fields.
    expected_value = {
        'idVendor': 'google',
        'idProduct': 'chromebook',
        'manufacturer': 'Google',
        'bcdDevice': 'foo'}
    self._WriteValue(self.tmp_dir, expected_value)

    func = usb.USBFunction(dir_path=self.tmp_dir)
    result = func()
    self.assertEquals(result, [expected_value])

  def testFail(self):
    # idVendor is not found.
    expected_value = {
        'idProduct': 'chromebook',
        'manufacturer': 'Google',
        'product': 'Chromebook',
        'bcdDevice': 'foo'}
    self._WriteValue(self.tmp_dir, expected_value)

    func = usb.USBFunction(dir_path=self.tmp_dir)
    result = func()
    self.assertEquals(result, [])

  def testMultipleResults(self):
    tmp_dir1 = os.path.join(self.tmp_dir, 'test1')
    os.mkdir(tmp_dir1)
    value1 = {
        'idVendor': 'google',
        'idProduct': 'chromebook',
        'manufacturer': 'Google',
        'product': 'Chromebook',
        'bcdDevice': 'foo'}
    self._WriteValue(tmp_dir1, value1)
    tmp_dir2 = os.path.join(self.tmp_dir, 'test2')
    os.mkdir(tmp_dir2)
    value2 = {
        'idVendor': 'apple',
        'idProduct': 'macbook',
        'manufacturer': 'Apple',
        'product': 'Macbook',
        'bcdDevice': 'bar'}
    self._WriteValue(tmp_dir2, value2)

    func = usb.USBFunction(dir_path=os.path.join(self.tmp_dir, 'test*'))
    result = func()
    self.assertEquals(sorted(result), sorted([value1, value2]))


if __name__ == '__main__':
  unittest.main()
