#!/usr/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101


import os
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.umpire import utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
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

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

    self.env = UmpireEnv()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.resources_dir)

    self.toolkit_resource = self.env.AddResource(TOOLKIT_PATH)

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testUnpack(self):
    expected_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                        TOOLKIT_MD5)
    self.assertEqual(expected_toolkit_dir,
                     utils.UnpackFactoryToolkit(self.env,
                                                self.toolkit_resource))
    self.assertTrue(os.path.exists(os.path.join(expected_toolkit_dir,
                                                UMPIRE_RELATIVE_PATH)))

    # Unpack server toolkit.
    expected_toolkit_dir = os.path.join(self.env.server_toolkits_dir,
                                        TOOLKIT_MD5)
    self.assertEqual(expected_toolkit_dir,
                     utils.UnpackFactoryToolkit(self.env, self.toolkit_resource,
                                                device_toolkit=False))
    self.assertTrue(os.path.exists(os.path.join(expected_toolkit_dir,
                                                UMPIRE_RELATIVE_PATH)))

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
