#!/usr/bin/python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire.server import config
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import umpired


TEST_DIR = os.path.dirname(__file__)

# If anything in UMPIRE_CONFIG_PATH file changed, update UMPIRE_CONFIG_RESOURCE
# by md5sum.
UMPIRE_CONFIG_PATH = os.path.join(TEST_DIR, 'testdata', 'default_umpire.yaml')
UMPIRE_CONFIG_RESOURCE = 'umpire.28395712fe81ce77465992a5e6be6ae9.yaml'

# Relative path of Umpire / Umpired executable.
UMPIRE_RELATIVE_PATH = os.path.join('bin', 'umpire')


class InitDaemonTest(unittest.TestCase):

  def setUp(self):
    self.root_dir = tempfile.mkdtemp()

    self.env = umpire_env.UmpireEnv(self.root_dir)
    self.env.base_dir = os.path.join(self.root_dir, common.DEFAULT_BASE_DIR)

    os.makedirs(os.path.join(self.root_dir, 'usr', 'local', 'bin'))
    os.makedirs(self.env.base_dir)
    os.makedirs(self.env.resources_dir)
    os.makedirs(self.env.server_toolkit_dir)

    self.umpire_bin_path = os.path.join(
        self.env.server_toolkit_dir, UMPIRE_RELATIVE_PATH)

    # pylint: disable=protected-access
    shutil.copyfile(UMPIRE_CONFIG_PATH,
                    os.path.join(self.env.server_toolkit_dir,
                                 umpired._DEFAULT_CONFIG_NAME))

  def tearDown(self):
    shutil.rmtree(self.root_dir)

  def VerifyDirectories(self):
    self.assertTrue(os.path.isdir(self.env.base_dir))
    for sub_dir in self.env.SUB_DIRS:
      self.assertTrue(os.path.isdir(os.path.join(self.env.base_dir, sub_dir)))

  def VerifyConfig(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.root_dir, 'var', 'db', 'factory', 'umpire', 'active_umpire.yaml')))
    self.assertTrue(self.env.InResource(UMPIRE_CONFIG_RESOURCE))

  def testDefault(self):
    umpired.InitDaemon(self.env)

    self.VerifyDirectories()
    self.VerifyConfig()

  def testReInit(self):
    umpired.InitDaemon(self.env)

    self.VerifyConfig()

    # Write active config.
    active_config = config.UmpireConfig(self.env.active_config_file,
                                        validate=False)
    self.assertNotEqual('modified active config',
                        active_config.GetDefaultBundle()['note'])
    active_config.GetDefaultBundle()['note'] = 'modified active config'
    active_config_yaml = active_config.Dump()

    umpired.InitDaemon(self.env)

    self.VerifyConfig()

    active_config = config.UmpireConfig(active_config_yaml, validate=False)
    self.assertEqual('modified active config',
                     active_config.GetDefaultBundle()['note'])


if __name__ == '__main__':
  unittest.main()
