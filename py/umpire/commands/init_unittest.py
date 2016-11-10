#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import init
from cros.factory.umpire import common as umpire_common
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire.umpire_env import UmpireEnv


TEST_DIR = os.path.dirname(__file__)

UMPIRE_CONFIG_PATH = os.path.join(TEST_DIR, 'testdata', 'default_umpire.yaml')
# The correct hash value of UMPIRE_CONFIG_RESOURCE can be obtained by:
#   `md5sum testdata/default_umpire.yaml | cut -b -8`
UMPIRE_CONFIG_RESOURCE = 'umpire.yaml##8db35cf5'

TEST_USER = 'umpire_user'
TEST_GROUP = 'umpire_group'

# Relative path of Umpire executable.
UMPIRE_RELATIVE_PATH = os.path.join('bin', 'umpire')


class InitTest(unittest.TestCase):

  def setUp(self):
    self.env = UmpireEnv()
    self.mox = mox.Mox()

    self.temp_dir = tempfile.mkdtemp()
    self.root_dir = os.path.join(self.temp_dir, 'root')
    self.env.base_dir = os.path.join(self.root_dir, 'var', 'db', 'factory',
                                     'umpire')
    os.makedirs(self.root_dir)
    os.makedirs(os.path.join(self.root_dir, 'usr', 'local', 'bin'))
    os.makedirs(self.env.base_dir)
    os.makedirs(self.env.resources_dir)

    self.umpire_bin_path = os.path.join(
        self.env.server_toolkit_dir, UMPIRE_RELATIVE_PATH)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    shutil.rmtree(self.temp_dir)

  def MockOsModule(self):
    # Mock out user.group id to current uid.gid.
    self.mox.StubOutWithMock(init, 'GetUidGid')
    init.GetUidGid(TEST_USER, TEST_GROUP).AndReturn(
        (os.getuid(), os.getgid()))

  def VerifyDirectories(self):
    self.assertTrue(os.path.isdir(self.env.base_dir))
    for sub_dir in self.env.SUB_DIRS:
      self.assertTrue(os.path.isdir(
          os.path.join(self.env.base_dir, sub_dir)))

    dummy_resource = os.path.join(self.env.resources_dir,
                                  umpire_common.DUMMY_RESOURCE)
    self.assertTrue(os.path.isfile(dummy_resource))
    self.assertEqual('', open(dummy_resource).read())

  def VerifyConfig(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.root_dir, 'var', 'db', 'factory', 'umpire', 'active_umpire.yaml')))
    self.assertTrue(self.env.InResource(UMPIRE_CONFIG_RESOURCE))

  def VerifyGlobalSymlink(self):
    umpire_default_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire')
    self.assertTrue(os.path.lexists(umpire_default_symlink))
    self.assertEqual(self.umpire_bin_path,
                     os.path.realpath(umpire_default_symlink))

  def testDefault(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    init.Init(self.env, False, TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_PATH)

    self.VerifyDirectories()
    self.VerifyConfig()
    self.VerifyGlobalSymlink()

  def testReInit(self):
    self.MockOsModule()
    # Expect mock call one more time.
    init.GetUidGid(TEST_USER, TEST_GROUP).AndReturn(
        (os.getuid(), os.getgid()))

    self.mox.ReplayAll()

    init.Init(self.env, False, TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_PATH)

    self.VerifyConfig()
    self.VerifyGlobalSymlink()

    # Write active config.
    active_config = umpire_config.UmpireConfig(self.env.active_config_file,
                                               validate=False)
    self.assertNotEqual('modified active config',
                        active_config.GetDefaultBundle()['note'])
    active_config.GetDefaultBundle()['note'] = 'modified active config'
    active_config.WriteFile(self.env.active_config_file)

    init.Init(self.env, False, TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_PATH)

    self.VerifyConfig()
    self.VerifyGlobalSymlink()

    active_config = umpire_config.UmpireConfig(self.env.active_config_file,
                                               validate=False)
    self.assertEqual('modified active config',
                     active_config.GetDefaultBundle()['note'])

  def testSetLocal(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    # local=True
    init.Init(self.env, True, TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_PATH)

    self.VerifyConfig()

    # Verify no symlink is created.
    self.assertFalse(os.path.exists(os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire')))


if __name__ == '__main__':
  unittest.main()
