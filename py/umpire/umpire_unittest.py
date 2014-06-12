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

TESTDATA_DIR = os.path.realpath(os.path.join(
    os.path.dirname(sys.modules[__name__].__file__), 'testdata'))
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
      os.unlink(os.path.join(bundle_path, 'factory_toolkit',
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


class UpdateTest(unittest.TestCase):
  FIRMWARE_PATH = os.path.join(TESTDATA_DIR, 'firmware.gz')
  TOOLKIT_PATH = os.path.join(TESTDATA_DIR, 'install_factory_toolkit.run')

  def setUp(self):
    self.env = UmpireEnv()
    self.args = Obj(source_id=None, dest_id=None, resources=list())
    self.mox = mox.Mox()
    self.mock_cli = None

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def CreateMockCLI(self):
    # Mock UmpireCLI XMLRPC connection.
    self.mox.StubOutWithMock(umpire, 'UmpireCLI')
    self.mock_cli = self.mox.CreateMockAnything()
    umpire.UmpireCLI(self.env).AndReturn(self.mock_cli)

  def testUpdateSingleResource(self):
    # Expect XMLRPC call.
    self.CreateMockCLI()
    self.mock_cli.Update([('factory_toolkit', self.TOOLKIT_PATH)], None, None)
    self.mox.ReplayAll()

    self.args.resources.append('factory_toolkit=%s' % self.TOOLKIT_PATH)
    umpire.Update(self.args, self.env)

  def testUpdateSingleResourceWithSourceDestId(self):
    # Expect XMLRPC call.
    self.CreateMockCLI()
    self.mock_cli.Update([('factory_toolkit', self.TOOLKIT_PATH)], 'bundle1',
                         'bundle2')
    self.mox.ReplayAll()

    self.args.resources.append('factory_toolkit=%s' % self.TOOLKIT_PATH)
    self.args.source_id = 'bundle1'
    self.args.dest_id = 'bundle2'
    umpire.Update(self.args, self.env)

  def testUpdateMultipleResources(self):
    # Expect XMLRPC call.
    self.CreateMockCLI()
    self.mock_cli.Update([('factory_toolkit', self.TOOLKIT_PATH),
                          ('firmware', self.FIRMWARE_PATH)], None, None)
    self.mox.ReplayAll()

    self.args.resources.append('factory_toolkit=%s' % self.TOOLKIT_PATH)
    self.args.resources.append('firmware=%s' % self.FIRMWARE_PATH)
    umpire.Update(self.args, self.env)

  def testUpdateInvalidResourceType(self):
    self.mox.ReplayAll()

    self.args.resources.append('wrong_res_type=%s' % self.TOOLKIT_PATH)
    self.assertRaisesRegexp(UmpireError, 'Unsupported resource type',
                            umpire.Update, self.args, self.env)

  def testUpdateInvalidResourceFile(self):
    self.mox.ReplayAll()

    self.args.resources.append('fsi=/path/to/nowhere')
    self.assertRaisesRegexp(IOError, 'Resource file not found',
                            umpire.Update, self.args, self.env)


class ImportBundleTest(unittest.TestCase):
  BUNDLE_PATH = os.path.join(TESTDATA_DIR, 'init_bundle')

  def setUp(self):
    self.env = UmpireEnv()
    self.args = Obj(id=None, bundle_path='.', note=None)
    self.mox = mox.Mox()

    # Mock UmpireCLI XMLRPC connection.
    self.mox.StubOutWithMock(umpire, 'UmpireCLI')
    self.mock_cli = self.mox.CreateMockAnything()
    umpire.UmpireCLI(self.env).AndReturn(self.mock_cli)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testImportBundle(self):
    # Expect XMLRPC call.
    self.mock_cli.ImportBundle(self.BUNDLE_PATH, 'new_bundle', 'new bundle')
    self.mox.ReplayAll()

    self.args.bundle_path = self.BUNDLE_PATH
    self.args.id = 'new_bundle'
    self.args.note = 'new bundle'
    umpire.ImportBundle(self.args, self.env)


class ImportResourceTest(unittest.TestCase):
  BUNDLE_PATH = os.path.join(TESTDATA_DIR, 'init_bundle')

  def setUp(self):
    self.env = UmpireEnv()
    self.args = Obj(resources=[])
    self.mox = mox.Mox()

    # Mock UmpireCLI XMLRPC connection.
    self.mox.StubOutWithMock(umpire, 'UmpireCLI')
    self.mock_cli = self.mox.CreateMockAnything()
    umpire.UmpireCLI(self.env).AndReturn(self.mock_cli)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testImportResource(self):
    with TempDirectory() as temp_dir:
      res_1 = os.path.join(temp_dir, 'res_1')
      WriteFile(res_1, '1')
      res_2 = os.path.join(temp_dir, 'res_1')
      WriteFile(res_1, '2')

      # Expect XMLRPC call.
      self.mock_cli.AddResource(res_1)
      self.mock_cli.AddResource(res_2)
      self.mox.ReplayAll()

      self.args.resources = [res_1, res_2]
      umpire.ImportResource(self.args, self.env)


if __name__ == '__main__':
  unittest.main()
