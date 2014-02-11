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
from cros.factory.umpire.commands import init
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils.file_utils import TouchFile
from cros.factory.utils import sys_utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
# Share ../testdata/init_bundle with ../umpire_unittest.
TEST_BUNDLE_DIR = os.path.join(TEST_DIR, '..', 'testdata', 'init_bundle')

# MD5SUM of install_factory_toolkit.run in TEST_BUNDLE_DIR
TOOLKIT_MD5 = '7509337e'

UMPIRE_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin', 'umpire')

class InitTest(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnv()
    self.mox = mox.Mox()

    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    self.root_dir = os.path.join(self.temp_dir, 'root')
    os.makedirs(self.root_dir)
    os.makedirs(os.path.join(self.root_dir, 'usr', 'local', 'bin'))

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    shutil.rmtree(self.temp_dir)

  def MockOsModule(self):
    # Mock out user.group id to current uid.gid.
    self.mox.StubOutWithMock(sys_utils, 'GetUidGid')
    sys_utils.GetUidGid('user', 'group').AndReturn((os.getuid(), os.getgid()))

  def VerifyToolkitInResource(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.env.resources_dir,
        'install_factory_toolkit.run##' + TOOLKIT_MD5)))

  def VerifyToolkitExtracted(self):
    self.assertTrue(os.path.exists(os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)))
    self.assertTrue(os.path.exists(os.path.join(
        self.env.client_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)))

  def testDefault(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    init.Init(self.env, TEST_BUNDLE_DIR, 'test_board', False, False, 'user',
              'group', root_dir=self.root_dir)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()

    # Verify symlinks.
    umpire_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)
    umpire_board_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire-test_board')
    self.assertTrue(os.path.exists(umpire_board_symlink))
    self.assertEqual(umpire_path, os.path.realpath(umpire_board_symlink))
    umpire_default_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire')
    self.assertTrue(os.path.exists(umpire_default_symlink))
    self.assertEqual(umpire_path, os.path.realpath(umpire_default_symlink))

  def testSetLocal(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    # local=True
    init.Init(self.env, TEST_BUNDLE_DIR, 'test_board', False, True, 'user',
              'group', root_dir=self.root_dir)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()

    # Verify no symlink is created.
    self.assertFalse(os.path.exists(os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire-test_board')))
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
    init.Init(self.env, TEST_BUNDLE_DIR, 'test_board', True, False, 'user',
              'group', root_dir=self.root_dir)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()

    # Verify symlinks.
    umpire_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)
    umpire_board_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire-test_board')
    self.assertTrue(os.path.exists(umpire_board_symlink))
    self.assertEqual(umpire_path, os.path.realpath(umpire_board_symlink))

    # /usr/local/bin/umpire is forced symlinked to umpire.
    self.assertTrue(os.path.exists(umpire_default_symlink))
    self.assertEqual(umpire_path, os.path.realpath(umpire_default_symlink))

  def testNoMakeDefault(self):
    self.MockOsModule()
    self.mox.ReplayAll()

    # Touch /usr/local/bin/umpire first to verify that Init doesn't change it.
    umpire_default_symlink = os.path.join(
          self.root_dir, 'usr', 'local', 'bin', 'umpire')
    TouchFile(umpire_default_symlink)

    # default=False
    init.Init(self.env, TEST_BUNDLE_DIR, 'test_board', False, False, 'user',
              'group', root_dir=self.root_dir)

    self.VerifyToolkitInResource()
    self.VerifyToolkitExtracted()

    # Verify symlinks.
    umpire_path = os.path.join(
        self.env.server_toolkits_dir, TOOLKIT_MD5, UMPIRE_RELATIVE_PATH)
    umpire_board_symlink = os.path.join(
        self.root_dir, 'usr', 'local', 'bin', 'umpire-test_board')
    self.assertTrue(os.path.exists(umpire_board_symlink))
    self.assertEqual(umpire_path, os.path.realpath(umpire_board_symlink))

    # /usr/local/bin/umpire is unchaged.
    self.assertTrue(os.path.exists(umpire_default_symlink))
    self.assertNotEqual(umpire_path, os.path.realpath(umpire_default_symlink))


if __name__ == '__main__':
  unittest.main()
