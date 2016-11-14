#!/usr/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101


import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import umpire_env
from cros.factory.umpire import utils
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(__file__)
TOOLKIT_PATH = os.path.join(TEST_DIR, 'testdata', 'install_factory_toolkit.run')
# MD5 and unpacked content of TOOLKIT
TOOLKIT_MD5 = '7509337e'
UMPIRE_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin', 'umpire')


class RegistryTest(unittest.TestCase):

  def testRegistry(self):
    reg = utils.Registry()
    reg['foo'] = 'value_foo'
    reg['bar'] = 'value_foo'

    test_reg = utils.Registry()
    self.assertEqual(test_reg.foo, 'value_foo')
    self.assertNotEqual(test_reg.bar, 'value_bar')


class UnpackFactoryToolkitTest(unittest.TestCase):
  DIR_MODE = 0755
  FILE_MODE_INSIDE_TOOLKIT = 0750

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()

    self.toolkit_resource = self.env.AddResource(TOOLKIT_PATH)

  def GetPermissionBits(self, path):
    FILE_PERMISSION_MASK = 0777
    return os.stat(path).st_mode & FILE_PERMISSION_MASK

  def testUnpackToolkit(self):
    expected_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                        TOOLKIT_MD5)
    self.assertEqual(
        expected_toolkit_dir,
        utils.UnpackFactoryToolkit(self.env, self.toolkit_resource,
                                   mode=self.DIR_MODE))
    umpire_path = os.path.join(expected_toolkit_dir, UMPIRE_RELATIVE_PATH)
    self.assertTrue(os.path.exists(umpire_path))

    # Exam file/directory permission.
    self.assertEqual(self.DIR_MODE,
                     self.GetPermissionBits(self.env.device_toolkits_dir))
    self.assertEqual(self.DIR_MODE,
                     self.GetPermissionBits(expected_toolkit_dir))

    # Exam MD5SUM file.
    expected_md5sum_path = os.path.join(expected_toolkit_dir, 'usr', 'local',
                                        'factory', 'MD5SUM')
    self.assertTrue(os.path.exists(expected_md5sum_path))
    self.assertEqual(0440, self.GetPermissionBits(expected_md5sum_path))
    self.assertEqual(TOOLKIT_MD5, file_utils.ReadFile(expected_md5sum_path))

  def testNoUnpackDestExist(self):
    expected_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                        TOOLKIT_MD5)
    # Create target directory.
    os.makedirs(expected_toolkit_dir)
    self.assertEqual(expected_toolkit_dir,
                     utils.UnpackFactoryToolkit(self.env,
                                                self.toolkit_resource))

    # Verify that the toolkit isn't unpacked to it.
    self.assertFalse(os.path.exists(os.path.join(expected_toolkit_dir,
                                                 UMPIRE_RELATIVE_PATH)))

  def testNoUnpackInvalidToolkitResource(self):
    self.assertIsNone(utils.UnpackFactoryToolkit(self.env, None))

if __name__ == '__main__':
  unittest.main()
