#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for config."""

import os
import unittest

from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.v3 import filesystem_adapter


_TEST_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), 'testdata', 'test_config.yaml')


class ConfigTest(unittest.TestCase):
  """Test for AppEngine config file."""
  # pylint: disable=protected-access

  def testConfigSwitchingDev(self):
    # Have to patch os.enviorn before importing config module
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'unknown project id'
    from cros.factory.hwid.service.appengine import config
    self.assertEqual('dev', config._Config(_TEST_CONFIG_PATH).env)

  def testConfigSwitchingProd(self):
    # Have to patch os.enviorn before importing config module
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'prod-project-name'
    from cros.factory.hwid.service.appengine import config
    self.assertEqual('prod', config._Config(_TEST_CONFIG_PATH).env)

  def testFileSystemType(self):
    from cros.factory.hwid.service.appengine import config
    self.assertTrue(
        issubclass(config.CONFIG.hwid_filesystem.__class__,
                   filesystem_adapter.FileSystemAdapter))

  def testHwidManagerType(self):
    from cros.factory.hwid.service.appengine import config
    self.assertTrue(
        issubclass(config.CONFIG.hwid_manager.__class__,
                   hwid_manager.HwidManager))


if __name__ == '__main__':
  unittest.main()
