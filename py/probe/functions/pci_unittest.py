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
from cros.factory.probe.functions import pci


class PCIFunctionTest(unittest.TestCase):
  def setUp(self):
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def _WriteValue(self, path, expected_value):
    if 'revision_id' in expected_value:
      with open(os.path.join(path, 'config'), 'wb') as f:
        f.write('0' * 8)
        f.write(chr(int(expected_value['revision_id'], 16)))
    for key in expected_value:
      if key == 'revision_id':
        continue
      with open(os.path.join(path, key), 'w') as f:
        f.write(expected_value[key])

  def testNormal(self):
    expected_value = {
        'vendor': 'google',
        'device': 'chromebook',
        'revision_id': '0x05'}
    self._WriteValue(self.tmp_dir, expected_value)

    func = pci.PCIFunction(dir_path=self.tmp_dir)
    result = func()
    self.assertEquals(result, [expected_value])

  def testFail(self):
    # device is not found.
    tmp_dir = os.path.join(self.tmp_dir, 'test1')
    os.mkdir(tmp_dir)
    value = {
        'vendor': 'apple',
        'revision_id': '0x05'}
    self._WriteValue(tmp_dir, value)

    func = pci.PCIFunction(dir_path=tmp_dir)
    result = func()
    self.assertEquals(result, [])

    # revision_id is not found.
    tmp_dir = os.path.join(self.tmp_dir, 'test2')
    os.mkdir(tmp_dir)
    value = {
        'vendor': 'apple',
        'device': 'macbook'}
    self._WriteValue(tmp_dir, value)

    func = pci.PCIFunction(dir_path=tmp_dir)
    result = func()
    self.assertEquals(result, [])

  def testMultipleResults(self):
    tmp_dir1 = os.path.join(self.tmp_dir, 'test1')
    os.mkdir(tmp_dir1)
    value1 = {
        'vendor': 'google',
        'device': 'chromebook',
        'revision_id': '0x05'}
    self._WriteValue(tmp_dir1, value1)
    tmp_dir2 = os.path.join(self.tmp_dir, 'test2')
    os.mkdir(tmp_dir2)
    value2 = {
        'vendor': 'apple',
        'device': 'macbook',
        'revision_id': '0x02'}
    self._WriteValue(tmp_dir2, value2)

    func = pci.PCIFunction(dir_path=os.path.join(self.tmp_dir, 'test*'))
    result = func()
    self.assertEquals(sorted(result), sorted([value1, value2]))


if __name__ == '__main__':
  unittest.main()
