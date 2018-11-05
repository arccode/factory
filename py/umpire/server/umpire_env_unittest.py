#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(os.path.dirname(__file__), 'testdata')
TEST_CONFIG = os.path.join(TESTDATA_DIR, 'minimal_empty_services_umpire.json')
TOOLKIT_DIR = os.path.join(TESTDATA_DIR, 'install_factory_toolkit.run')
TEST_PARAMETER = os.path.join(TESTDATA_DIR, 'test_parameter.json')


class UmpireEnvTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    self.mox = mox.Mox()
    parameter_json_file = self.env.parameter_json_file
    shutil.copy(TEST_PARAMETER, parameter_json_file)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    self.env.Close()

  def testLoadConfigDefault(self):
    default_path = os.path.join(self.env.base_dir, 'active_umpire.json')
    shutil.copy(TEST_CONFIG, default_path)

    self.env.LoadConfig()
    self.assertEqual(default_path, self.env.config_path)

  def testLoadConfigCustomPath(self):
    custom_path = os.path.join(self.env.base_dir, 'custom_config.json')
    shutil.copy(TEST_CONFIG, custom_path)

    self.env.LoadConfig(custom_path=custom_path)
    self.assertEqual(custom_path, self.env.config_path)

  def testActivateConfigFile(self):
    file_utils.TouchFile(self.env.active_config_file)
    config_to_activate = os.path.join(self.env.base_dir, 'to_activate.json')
    file_utils.TouchFile(config_to_activate)

    self.env.ActivateConfigFile(config_path=config_to_activate)
    self.assertTrue(os.path.exists(self.env.active_config_file))
    self.assertEqual(config_to_activate,
                     os.path.realpath(self.env.active_config_file))

  def testGetResourcePath(self):
    resource_path = self.env.AddConfigFromBlob(
        'hello', resource.ConfigTypeNames.umpire_config)
    resource_name = os.path.basename(resource_path)

    self.assertTrue(resource_path, self.env.GetResourcePath(resource_name))

  def testGetResourcePathNotFound(self):
    self.assertRaises(IOError, self.env.GetResourcePath, 'foobar')

    # Without check, just output resource_dir/resource_name
    self.assertEqual(os.path.join(self.env.resources_dir, 'foobar'),
                     self.env.GetResourcePath('foobar', check=False))

  def testQueryParameters(self):
    # Query w.sh in parent directory
    query_file = self.env.QueryParameters(None, 'w.sh')
    self.assertEqual(query_file, [('w.sh', 'some/path/w0.sh')])

    # Query all components under dir0/dir1
    query_namespace = self.env.QueryParameters('dir0/dir1', None)
    self.assertEqual(query_namespace, [('x.json', 'some/path/x2.json'),
                                       ('a.html', 'some/path/a1.html')])

    # Query not existed component
    query_error = self.env.QueryParameters('dir0', 'not_existed_file')
    self.assertEqual(query_error, [])

  def testUpdateParameterComponent(self):
    test_file_path = os.path.join(self.env.base_dir, 'test.txt')
    file_utils.TouchFile(test_file_path)

    # Create new component
    component = self.env.UpdateParameterComponent(None, 0, 'test.txt', None,
                                                  test_file_path)
    self.assertEqual(component, {
        'id': 3,
        'dir_id': 0,
        'name': 'test.txt',
        'revisions': [self.env.GetParameterDstPath(test_file_path)],
        'using_ver': 0
    })

    # Update version
    component = self.env.UpdateParameterComponent(0, None, 'w.sh', None,
                                                  test_file_path)
    self.assertEqual(component, {
        'id': 0,
        'dir_id': None,
        'name': 'w.sh',
        'revisions': [
            'some/path/w0.sh',
            self.env.GetParameterDstPath(test_file_path)
        ],
        'using_ver': 1
    })

    # Update version and change version at the same time
    self.assertRaises(common.UmpireError, self.env.UpdateParameterComponent,
                      0, None, 'w.sh', 1, test_file_path)

    # Changing to invalid version
    self.assertRaises(common.UmpireError, self.env.UpdateParameterComponent,
                      0, None, 'w.sh', 10, None)

  def testCreateParameterDirectory(self):
    # Create directory
    directory = self.env.CreateParameterDirectory(0, 'dir2')
    self.assertEqual(directory, {
        'id': 2,
        'name': 'dir2',
        'parent_id': 0
    })


if __name__ == '__main__':
  unittest.main()
