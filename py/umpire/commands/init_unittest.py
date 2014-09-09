#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import os
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common as umpire_common
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire.commands import init
from cros.factory.umpire.commands import system
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils.file_utils import TouchFile
from cros.factory.utils import sys_utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
# Share ../testdata/init_bundle with ../umpire_unittest.
TEST_BUNDLE_DIR = os.path.join(TEST_DIR, '..', 'testdata', 'init_bundle')

UMPIRE_CONFIG_TEMPLATE_PATH = os.path.join(TEST_DIR, 'testdata',
                                           'umpired_template.yaml')
UMPIRE_CONFIG_RESOURCE = 'umpire.yaml##a2e913b7'

# MD5SUM of install_factory_toolkit.run in TEST_BUNDLE_DIR
TOOLKIT_MD5 = '43bc8d96'

TEST_USER = 'umpire_user'
TEST_GROUP = 'umpire_group'
TEST_BOARD = 'testboard'

# Relative path of Umpire / Umpired executable.
UMPIRE_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin', 'umpire')
UMPIRED_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin',
                                     'umpired')

# Relative path of board specific Umpire bin symlink.
BOARD_SPECIFIC_UMPIRE_BIN_SYMLINK = os.path.join(
    'usr', 'local', 'bin', 'umpire-' + TEST_BOARD)

class InitTest(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnv()
    self.mox = mox.Mox()
    # Stub out system related calls.
    self.mox.StubOutWithMock(system, 'CreateUmpireUpstart')
    self.mox.StubOutWithMock(system, 'StartUmpire')
    self.mox.StubOutWithMock(system, 'StopUmpire')
    system.CreateUmpireUpstart()
    system.StartUmpire(TEST_BOARD)
    system.StopUmpire(TEST_BOARD)

    self.temp_dir = tempfile.mkdtemp()
    self.root_dir = os.path.join(self.temp_dir, 'root')
    self.env.base_dir = os.path.join(self.root_dir, 'var', 'db', 'factory',
                                     'umpire', TEST_BOARD)
    os.makedirs(self.root_dir)
    os.makedirs(os.path.join(self.root_dir, 'usr', 'local', 'bin'))
    os.makedirs(self.env.base_dir)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    shutil.rmtree(self.temp_dir)

  def MockOsModule(self):
    # Mock out user.group id to current uid.gid.
    self.mox.StubOutWithMock(sys_utils, 'GetUidGid')
    sys_utils.GetUidGid(TEST_USER, TEST_GROUP).AndReturn(
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


  def VerifyToolkitInResource(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.env.resources_dir,
        'install_factory_toolkit.run##' + TOOLKIT_MD5)))

  def VerifyToolkitExtracted(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)))
    self.assertTrue(os.path.exists(os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRED_RELATIVE_PATH)))

  def VerifyConfig(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.root_dir, 'var', 'db', 'factory', 'umpire', TEST_BOARD,
        'active_umpire.yaml')))
    self.assertTrue(self.env.InResource(UMPIRE_CONFIG_RESOURCE))

  def VerifyLocalSymlink(self):
    umpire_bin_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)
    umpire_bin_symlink = os.path.join(self.env.bin_dir, 'umpire')
    self.assertTrue(os.path.exists(umpire_bin_symlink))
    self.assertEqual(umpire_bin_path, os.path.realpath(umpire_bin_symlink))

    umpired_bin_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRED_RELATIVE_PATH)
    umpired_bin_symlink = os.path.join(self.env.bin_dir, 'umpired')
    self.assertTrue(os.path.exists(umpired_bin_symlink))
    self.assertEqual(umpired_bin_path, os.path.realpath(umpired_bin_symlink))

  def VerifyGlobalSymlink(self):
    umpire_bin_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)
    umpire_board_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire-testboard')
    self.assertTrue(os.path.exists(umpire_board_symlink))
    self.assertEqual(umpire_bin_path, os.path.realpath(umpire_board_symlink))
    umpire_default_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire')
    self.assertTrue(os.path.exists(umpire_default_symlink))
    self.assertEqual(umpire_bin_path, os.path.realpath(umpire_default_symlink))

  def testDefault(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    init.Init(self.env, TEST_BUNDLE_DIR, TEST_BOARD, False, False,
              TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_TEMPLATE_PATH)

    self.VerifyDirectories()
    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()
    self.VerifyConfig()
    self.VerifyLocalSymlink()
    self.VerifyGlobalSymlink()

  def testReInit(self):
    self.MockOsModule()
    # Expect mock call ne more time.
    system.CreateUmpireUpstart()
    system.StartUmpire(TEST_BOARD)
    system.StopUmpire(TEST_BOARD)
    sys_utils.GetUidGid(TEST_USER, TEST_GROUP).AndReturn(
        (os.getuid(), os.getgid()))

    self.mox.ReplayAll()

    init.Init(self.env, TEST_BUNDLE_DIR, TEST_BOARD, False, False,
              TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_TEMPLATE_PATH)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()
    self.VerifyConfig()
    self.VerifyLocalSymlink()
    self.VerifyGlobalSymlink()

    # Write active config.
    active_config = umpire_config.UmpireConfig(self.env.active_config_file,
                                               validate=False)
    self.assertNotEqual('modified active config',
                        active_config.GetDefaultBundle()['note'])
    active_config.GetDefaultBundle()['note'] = 'modified active config'
    active_config.WriteFile(self.env.active_config_file)

    init.Init(self.env, TEST_BUNDLE_DIR, TEST_BOARD, False, False,
              TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_TEMPLATE_PATH)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()
    self.VerifyConfig()
    self.VerifyLocalSymlink()
    self.VerifyGlobalSymlink()

    active_config = umpire_config.UmpireConfig(self.env.active_config_file,
                                               validate=False)
    self.assertEqual('modified active config',
                     active_config.GetDefaultBundle()['note'])


  def testSetLocal(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    # local=True
    init.Init(self.env, TEST_BUNDLE_DIR, TEST_BOARD, False, True, TEST_USER,
              TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_TEMPLATE_PATH)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()
    self.VerifyConfig()
    self.VerifyLocalSymlink()

    # Verify no symlink is created.
    self.assertFalse(os.path.exists(os.path.join(
        self.root_dir, BOARD_SPECIFIC_UMPIRE_BIN_SYMLINK)))
    self.assertFalse(os.path.exists(os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire')))

  def testMakeDefault(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    # Touch /usr/local/bin/umpire first to verify that Init changes it
    # to symlink to umpire bin.
    umpire_default_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire')
    TouchFile(umpire_default_symlink)

    # make_default=True
    init.Init(self.env, TEST_BUNDLE_DIR, TEST_BOARD, True, False, TEST_USER,
              TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_TEMPLATE_PATH)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()
    self.VerifyConfig()
    self.VerifyLocalSymlink()
    # /usr/local/bin/umpire is forced symlinked to umpire.
    self.VerifyGlobalSymlink()

  def testNoMakeDefault(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    # Touch /usr/local/bin/umpire first to verify that Init doesn't change it.
    umpire_default_symlink = os.path.join(
          self.root_dir, 'usr', 'local', 'bin', 'umpire')
    TouchFile(umpire_default_symlink)

    # default=False
    init.Init(self.env, TEST_BUNDLE_DIR, TEST_BOARD, False, False,
              TEST_USER, TEST_GROUP, root_dir=self.root_dir,
              config_template=UMPIRE_CONFIG_TEMPLATE_PATH)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()
    self.VerifyConfig()
    self.VerifyLocalSymlink()

    # Verify symlinks.
    umpire_bin_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)
    umpire_board_symlink = os.path.join(
        self.root_dir, BOARD_SPECIFIC_UMPIRE_BIN_SYMLINK)
    self.assertTrue(os.path.exists(umpire_board_symlink))
    self.assertEqual(umpire_bin_path, os.path.realpath(umpire_board_symlink))

    # /usr/local/bin/umpire is unchaged.
    self.assertTrue(os.path.exists(umpire_default_symlink))
    self.assertNotEqual(umpire_bin_path,
                        os.path.realpath(umpire_default_symlink))


if __name__ == '__main__':
  unittest.main()
