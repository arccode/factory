#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
from mox import IsA
import os
import shutil
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.common import Obj
from cros.factory.utils.file_utils import TempDirectory, WriteFile
from cros.factory.umpire.commands import init
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire import umpire
from cros.factory.umpire.umpire_env import UmpireEnv

TESTDATA_DIR = os.path.join(os.path.dirname(sys.modules[__name__].__file__),
                            'testdata')
DEFAULT_BUNDLE = os.path.join(TESTDATA_DIR, 'init_bundle')

class InitTest(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnv()
    self.args = Obj(base_dir=None, board=None, bundle_path=DEFAULT_BUNDLE,
                    default=False, local=False, user='user', group='group')
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testDefault(self):
    self.mox.StubOutWithMock(init, 'Init')
    # args.board is unassigned, so extract 'board' from MANIFEST.
    init.Init(IsA(UmpireEnv), DEFAULT_BUNDLE, 'test_board', False, False,
              'user', 'group')
    self.mox.ReplayAll()

    umpire.Init(self.args, self.env)
    self.assertEqual('/var/db/factory/umpire/test_board', self.env.base_dir)

  def testSpecifyBoard(self):
    BOARD_ARG = 'board_from_args'
    self.mox.StubOutWithMock(init, 'Init')
    init.Init(IsA(UmpireEnv), DEFAULT_BUNDLE, BOARD_ARG, False, False,
              'user', 'group')
    self.mox.ReplayAll()

    self.args.board = BOARD_ARG
    umpire.Init(self.args, self.env)
    self.assertEqual('/var/db/factory/umpire/' + BOARD_ARG, self.env.base_dir)

  def testFailedToDeriveBoard(self):
    with TempDirectory() as temp_dir:
      # Prepare a factory bundle with MANIFEST without board.
      bundle_path = os.path.join(temp_dir, 'bundle')
      shutil.copytree(DEFAULT_BUNDLE, bundle_path)
      WriteFile(os.path.join(bundle_path, 'MANIFEST.yaml'), 'missing board\n')

      self.args.bundle_path = bundle_path
      self.assertRaisesRegexp(UmpireError, 'Unable to resolve board name',
                              umpire.Init, self.args, self.env)

  def testManifestMissing(self):
    with TempDirectory() as temp_dir:
      # Prepare a factory bundle without MANIFEST
      bundle_path = os.path.join(temp_dir, 'bundle')
      shutil.copytree(DEFAULT_BUNDLE, bundle_path)
      os.unlink(os.path.join(bundle_path, 'MANIFEST.yaml'))

      self.args.bundle_path = bundle_path
      self.assertRaisesRegexp(IOError, 'Missing factory bundle manifest',
                              umpire.Init, self.args, self.env)

  def testFactoryToolkitMissing(self):
    with TempDirectory() as temp_dir:
      # Prepare a factory bundle without factory toolkit
      bundle_path = os.path.join(temp_dir, 'bundle')
      shutil.copytree(DEFAULT_BUNDLE, bundle_path)
      os.unlink(os.path.join(bundle_path, 'factory_test',
                             'install_factory_toolkit.run'))

      self.args.bundle_path = bundle_path
      self.assertRaisesRegexp(IOError, 'Missing factory toolkit',
                              umpire.Init, self.args, self.env)


  def testSpecifyBaseDir(self):
    self.mox.StubOutWithMock(init, 'Init')
    init.Init(IsA(UmpireEnv), DEFAULT_BUNDLE, 'test_board', False, False,
              'user', 'group')
    self.mox.ReplayAll()

    self.args.base_dir = '/tmp/base_dir'
    umpire.Init(self.args, self.env)
    self.assertEqual('/tmp/base_dir', self.env.base_dir)


if __name__ == '__main__':
  unittest.main()
