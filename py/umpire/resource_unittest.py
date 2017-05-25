#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import resource
from cros.factory.umpire import umpire_env
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(__file__)
TESTDATA_DIR = os.path.join(TEST_DIR, 'testdata')
TOOLKIT_PATH = os.path.join(TESTDATA_DIR, 'install_factory_toolkit.run')
# MD5 and unpacked content of TOOLKIT
TOOLKIT_MD5 = '7509337e60c7facd302236ecdb1af473'
UMPIRE_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin', 'umpire')


class UnpackFactoryToolkitTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()

  def tearDown(self):
    self.env.Close()

  def testUnpackToolkit(self):
    resource.UnpackFactoryToolkit(self.env, TOOLKIT_PATH, TOOLKIT_MD5)
    expected_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                        TOOLKIT_MD5)
    umpire_path = os.path.join(expected_toolkit_dir, UMPIRE_RELATIVE_PATH)
    self.assertTrue(os.path.exists(umpire_path))

    # Exam MD5SUM file.
    expected_md5sum_path = os.path.join(expected_toolkit_dir,
                                        'usr', 'local', 'factory', 'MD5SUM')
    self.assertTrue(os.path.exists(expected_md5sum_path))
    self.assertEqual(TOOLKIT_MD5,
                     file_utils.ReadFile(expected_md5sum_path).rstrip())


if __name__ == '__main__':
  unittest.main()
