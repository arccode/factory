#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for config."""

import os
import unittest

import factory_common  #pylint: disable=unused-import
from cros.factory.hwid.service.appengine import filesystem_adapter
from cros.factory.hwid.service.appengine import hwid_manager


class ConfigTest(unittest.TestCase):
  """Test for AppEngine config file."""

  def testConfigSwitchingDev(self):
    # Have to patch os.enviorn before importing config module
    os.environ['APPLICATION_ID'] = 'unknown app id'
    from cros.factory.hwid.service.appengine import config
    self.assertEqual('dev', config.GetConfig()['env'])

  def testConfigSwitchingProd(self):
    # Have to patch os.enviorn before importing config module
    os.environ['APPLICATION_ID'] = 's~google.com:chromeoshwid'
    from cros.factory.hwid.service.appengine import config
    self.assertEqual('prod', config.GetConfig()['env'])

  def testFileSystemType(self):
    from cros.factory.hwid.service.appengine import config
    self.assertTrue(
        issubclass(config.hwid_filesystem.__class__,
                   filesystem_adapter.FileSystemAdapter))

  def testHwidManagerType(self):
    from cros.factory.hwid.service.appengine import config
    self.assertTrue(
        issubclass(config.hwid_manager.__class__, hwid_manager.HwidManager))


if __name__ == '__main__':
  unittest.main()
