#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs


class SysfsFunctionTest(unittest.TestCase):
  def setUp(self):
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def testNormal(self):
    with open(os.path.join(self.tmp_dir, 'vendor'), 'w') as f:
      f.write('google\n')
    with open(os.path.join(self.tmp_dir, 'device'), 'w') as f:
      f.write('chromebook\n')

    func = sysfs.SysfsFunction(dir_path=self.tmp_dir, keys=['vendor', 'device'])
    result = func()
    self.assertEquals(result, [{'vendor': 'google', 'device': 'chromebook'}])

  def testOptionalKeys(self):
    with open(os.path.join(self.tmp_dir, 'device'), 'w') as f:
      f.write('chromebook\n')
    with open(os.path.join(self.tmp_dir, 'optional_1'), 'w') as f:
      f.write('OPTIONAL_1\n')

    func = sysfs.SysfsFunction(
        dir_path=self.tmp_dir, keys=['device'],
        optional_keys=['optional_1', 'optional_2'])
    result = func()
    self.assertEquals(result, [{'device': 'chromebook',
                                'optional_1': 'OPTIONAL_1'}])

  def testFail(self):
    """Device is not found."""
    with open(os.path.join(self.tmp_dir, 'vendor'), 'w') as f:
      f.write('google\n')

    func = sysfs.SysfsFunction(dir_path=self.tmp_dir, keys=['vendor', 'device'])
    result = func()
    self.assertEquals(result, [])

  def testMultipleResults(self):
    os.mkdir(os.path.join(self.tmp_dir, 'foo'))
    with open(os.path.join(self.tmp_dir, 'foo', 'vendor'), 'w') as f:
      f.write('google\n')
    with open(os.path.join(self.tmp_dir, 'foo', 'device'), 'w') as f:
      f.write('chromebook\n')
    os.mkdir(os.path.join(self.tmp_dir, 'bar'))
    with open(os.path.join(self.tmp_dir, 'bar', 'vendor'), 'w') as f:
      f.write('apple\n')
    with open(os.path.join(self.tmp_dir, 'bar', 'device'), 'w') as f:
      f.write('macbook\n')

    with open(os.path.join(self.tmp_dir, 'NOT_DIR'), 'w') as f:
      f.write('SHOULD NOT BE PROBED.')

    func = sysfs.SysfsFunction(dir_path=os.path.join(self.tmp_dir, '*'),
                               keys=['vendor', 'device'])
    result = func()
    self.assertEquals(sorted(result),
                      sorted([{'vendor': 'google', 'device': 'chromebook'},
                              {'vendor': 'apple', 'device': 'macbook'}]))


if __name__ == '__main__':
  unittest.main()
