#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import unittest

from cros.factory.umpire.server.commands import parameters
from cros.factory.umpire import common
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import file_utils


TESTDATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'testdata')
TEST_PARAMETER = os.path.join(TESTDATA_DIR, 'test_parameter.json')


class ParametersTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    parameter_json_file = self.env.parameter_json_file
    shutil.copy(TEST_PARAMETER, parameter_json_file)
    self.parameters = parameters.Parameters(self.env)

  def tearDown(self):
    self.env.Close()

  def testQueryParameters(self):
    # Query w.sh in parent directory
    query_file = self.parameters.QueryParameters(None, 'w.sh')
    self.assertEqual(query_file, [('w.sh', 'some/path/w0.sh')])

    # Query all components under dir0/dir1
    query_namespace = self.parameters.QueryParameters('dir0/dir1', None)
    self.assertEqual(query_namespace, [('x.json', 'some/path/x2.json'),
                                       ('a.html', 'some/path/a1.html')])

    # Query not existed component
    query_error = self.parameters.QueryParameters('dir0', 'not_existed_file')
    self.assertEqual(query_error, [])

  def testUpdateParameterComponent(self):
    test_file_path = os.path.join(self.env.base_dir, 'test.txt')
    file_utils.TouchFile(test_file_path)

    # Create new component
    component = self.parameters.UpdateParameterComponent(
        None, 0, 'test.txt', None, test_file_path)
    self.assertEqual(component, {
        'id': 3,
        'dir_id': 0,
        'name': 'test.txt',
        'revisions': [self.parameters.GetParameterDstPath(test_file_path)],
        'using_ver': 0
    })

    # Update version
    component = self.parameters.UpdateParameterComponent(
        0, None, 'w.sh', None, test_file_path)
    self.assertEqual(component, {
        'id': 0,
        'dir_id': None,
        'name': 'w.sh',
        'revisions': [
            'some/path/w0.sh',
            self.parameters.GetParameterDstPath(test_file_path)
        ],
        'using_ver': 1
    })

    # Update version and change version at the same time
    self.assertRaises(common.UmpireError,
                      self.parameters.UpdateParameterComponent, 0, None, 'w.sh',
                      1, test_file_path)

    # Changing to invalid version
    self.assertRaises(common.UmpireError,
                      self.parameters.UpdateParameterComponent, 0, None, 'w.sh',
                      10, None)

  def testUpdateParameterDirectory(self):
    # Create directory
    directory = self.parameters.UpdateParameterDirectory(None, 0, 'dir2')
    self.assertEqual(directory, {
        'id': 2,
        'name': 'dir2',
        'parent_id': 0
    })

    # Rename directory
    directory = self.parameters.UpdateParameterDirectory(1, None, 'dir1.1')
    self.assertEqual(directory, {
        'id': 1,
        'name': 'dir1.1',
        'parent_id': 0
    })


if __name__ == '__main__':
  unittest.main()
