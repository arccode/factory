#!/usr/bin/env python3
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

from cros.factory.probe.functions import file as file_module
from cros.factory.utils import file_utils


class FileFunctionTest(unittest.TestCase):
  def setUp(self):
    self.tmp_file = file_utils.CreateTemporaryFile()
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.remove(self.tmp_file)
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def testSingleLineFile(self):
    content = 'hello, world.  \n'
    with open(self.tmp_file, 'w') as f:
      f.write(content)

    # Use default key.
    func = file_module.FileFunction(file_path=self.tmp_file)
    result = func()
    self.assertEqual(result, [{file_module.DEFAULT_FILE_KEY: 'hello, world.'}])

    # Assign the key of the result.
    func = file_module.FileFunction(file_path=self.tmp_file, key='hello')
    result = func()
    self.assertEqual(result, [{'hello': 'hello, world.'}])

  def testMultipleLinesFile(self):
    content = 'foo  \n  \nbar  \n'
    with open(self.tmp_file, 'w') as f:
      f.write(content)

    # Not split line, only return one result.
    func = file_module.FileFunction(file_path=self.tmp_file, key='idx')
    result = func()
    self.assertEqual(result, [{'idx': 'foo  \n  \nbar'}])

    # Split line, return multiple results.
    func = file_module.FileFunction(
        file_path=self.tmp_file, key='idx', split_line=True)
    result = func()
    self.assertEqual(sorted(result, key=lambda d: sorted(d.items())),
                     sorted([{'idx': 'foo'}, {'idx': 'bar'}],
                            key=lambda d: sorted(d.items())))

  def testMultipleFiles(self):
    with open(os.path.join(self.tmp_dir, 'foo1'), 'w') as f:
      f.write('FOO1')
    with open(os.path.join(self.tmp_dir, 'foo2'), 'w') as f:
      f.write('FOO2')
    with open(os.path.join(self.tmp_dir, 'bar'), 'w') as f:
      f.write('BAR')

    func = file_module.FileFunction(
        file_path=os.path.join(self.tmp_dir, '*'), key='idx')
    result = func()
    self.assertEqual(sorted(result, key=lambda d: sorted(d.items())),
                     sorted([{'idx': 'FOO1'}, {'idx': 'FOO2'}, {'idx': 'BAR'}],
                            key=lambda d: sorted(d.items())))

    func = file_module.FileFunction(
        file_path=os.path.join(self.tmp_dir, 'foo*'), key='idx')
    result = func()
    self.assertEqual(sorted(result, key=lambda d: sorted(d.items())),
                     sorted([{'idx': 'FOO1'}, {'idx': 'FOO2'}],
                            key=lambda d: sorted(d.items())))

  def testEmptyResult(self):
    # tmp_file is empty.
    func = file_module.FileFunction(file_path=self.tmp_file, key='idx')
    result = func()
    self.assertEqual(result, [])

    # tmp_dir is empty.
    func = file_module.FileFunction(
        file_path=os.path.join(self.tmp_dir, '*'), key='idx')
    result = func()
    self.assertEqual(result, [])


if __name__ == '__main__':
  unittest.main()
