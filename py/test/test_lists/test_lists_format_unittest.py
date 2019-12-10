#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import glob
import os
import unittest

from cros.factory.test.env import paths
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class JSONFormatTest(unittest.TestCase):
  def testFormatted(self):
    test_lists = glob.glob(
        os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR, 'test', 'test_lists',
                     '*.test_list.json'))
    formatter = os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR, 'tools',
                             'format_json_test_list.py')

    failed_files = []
    for test_list in test_lists:
      if file_utils.ReadFile(test_list) != process_utils.CheckOutput(
          [formatter, test_list]):
        failed_files.append(test_list)

    self.assertFalse(
        failed_files,
        ('files %r are not properly formatted, please run '
         '"py/tools/format_json_test_list.py -i" on these files.') %
        failed_files)


if __name__ == '__main__':
  unittest.main()
