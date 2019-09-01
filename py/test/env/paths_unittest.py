#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths

class GetFactoryPythonArchivePathUnittest(unittest.TestCase):
  def setUp(self):
    pass

  def testLocalFactoryPythonArchiveRegularParExists(self):
    paths.sys_utils.GetRunningFactoryPythonArchivePath = lambda: None
    paths.os.path.exists = mock.MagicMock(
        side_effect=lambda p: p.endswith('factory.par'))
    expected = os.path.join(paths.FACTORY_DIR, 'factory.par')

    self.assertEqual(paths.GetFactoryPythonArchivePath(), expected)

  def testLocalFactoryPythonArchiveMiniParExists(self):
    paths.sys_utils.GetRunningFactoryPythonArchivePath = lambda: None
    expected = os.path.join(paths.FACTORY_DIR, 'factory-mini.par')
    paths.os.path.exists = mock.MagicMock(
        side_effect=lambda p: p == expected)

    self.assertEqual(paths.GetFactoryPythonArchivePath(), expected)

  def testLocalFactoryPythonArchiveTestImageMiniParExists(self):
    expected = '/usr/local/factory-mini/factory-mini.par'
    paths.sys_utils.GetRunningFactoryPythonArchivePath = lambda: None
    paths.os.path.exists = mock.MagicMock(
        side_effect=lambda p: p == expected)

    self.assertEqual(paths.GetFactoryPythonArchivePath(), expected)

  def testLocalFactoryPythonArchiveParNotExists(self):
    paths.sys_utils.GetRunningFactoryPythonArchivePath = lambda: None
    paths.os.path.exists = mock.MagicMock(return_value=False)

    with self.assertRaisesRegexp(EnvironmentError,
                                 'cannot find factory python archive'):
      unused_var = paths.GetFactoryPythonArchivePath()

  def testLocalFactoryPythonArchiveRunningPar(self):
    expected = '/path/to/running/factory/par'
    paths.sys_utils.GetRunningFactoryPythonArchivePath = lambda: expected

    self.assertEqual(paths.GetFactoryPythonArchivePath(), expected)


if __name__ == '__main__':
  unittest.main()
