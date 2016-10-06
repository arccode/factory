#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import __builtin__  # Used for mocking raw_input().
import mox
import os
import shutil
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import init
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire import umpire
from cros.factory.utils.file_utils import TempDirectory
from cros.factory.utils.file_utils import WriteFile
from cros.factory.utils.type_utils import Obj


TESTDATA_DIR = os.path.realpath(os.path.join(
    os.path.dirname(sys.modules[__name__].__file__), 'testdata'))
DEFAULT_BUNDLE = os.path.join(TESTDATA_DIR, 'init_bundle')


def GetStdout():
  """Gets stdout buffer.

  Needs unittest.main(buffer=True).
  """
  # pylint: disable=E1101
  # getvalue is set when unittest.main has buffer=True arg.
  output = sys.stdout.getvalue()
  # pylint: enable=E1101
  return output.split('\n')


class InitTest(unittest.TestCase):

  def setUp(self):
    self.args = Obj(base_dir=None, board=None, bundle_path=DEFAULT_BUNDLE,
                    default=False, local=False, user='user', group='group')
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testDefault(self):
    def EnvBaseDirMatcher(env):
      return env.base_dir == '/var/db/factory/umpire/test_board'

    self.mox.StubOutWithMock(init, 'Init')
    # args.board is unassigned, so extract 'board' from MANIFEST.
    init.Init(mox.Func(EnvBaseDirMatcher), DEFAULT_BUNDLE, 'test_board', False,
              False, 'user', 'group')
    self.mox.ReplayAll()

    umpire.Init(self.args)

  def testSpecifyBoard(self):
    BOARD_ARG = 'board_from_args'

    def EnvBaseDirMatcher(env):
      return env.base_dir == '/var/db/factory/umpire/' + BOARD_ARG

    self.mox.StubOutWithMock(init, 'Init')
    init.Init(mox.Func(EnvBaseDirMatcher), DEFAULT_BUNDLE, BOARD_ARG, False,
              False, 'user', 'group')
    self.mox.ReplayAll()

    self.args.board = BOARD_ARG
    umpire.Init(self.args)

  def testFailedToDeriveBoard(self):
    with TempDirectory() as temp_dir:
      # Prepare a factory bundle with MANIFEST without board.
      bundle_path = os.path.join(temp_dir, 'bundle')
      shutil.copytree(DEFAULT_BUNDLE, bundle_path)
      WriteFile(os.path.join(bundle_path, 'MANIFEST.yaml'), 'missing board\n')

      self.args.bundle_path = bundle_path
      self.assertRaisesRegexp(UmpireError, 'Unable to resolve board name',
                              umpire.Init, self.args)

  def testManifestMissing(self):
    with TempDirectory() as temp_dir:
      # Prepare a factory bundle without MANIFEST
      bundle_path = os.path.join(temp_dir, 'bundle')
      shutil.copytree(DEFAULT_BUNDLE, bundle_path)
      os.unlink(os.path.join(bundle_path, 'MANIFEST.yaml'))

      self.args.bundle_path = bundle_path
      self.assertRaisesRegexp(IOError, 'Missing factory bundle manifest',
                              umpire.Init, self.args)

  def testFactoryToolkitMissing(self):
    with TempDirectory() as temp_dir:
      # Prepare a factory bundle without factory toolkit
      bundle_path = os.path.join(temp_dir, 'bundle')
      shutil.copytree(DEFAULT_BUNDLE, bundle_path)
      os.unlink(os.path.join(bundle_path, 'factory_toolkit',
                             'install_factory_toolkit.run'))

      self.args.bundle_path = bundle_path
      self.assertRaisesRegexp(IOError, 'Missing factory toolkit',
                              umpire.Init, self.args)

  def testSpecifyBaseDir(self):
    BASE_DIR = '/tmp/base_dir'

    def EnvBaseDirMatcher(env):
      return env.base_dir == BASE_DIR

    self.mox.StubOutWithMock(init, 'Init')
    init.Init(mox.Func(EnvBaseDirMatcher), DEFAULT_BUNDLE, 'test_board', False,
              False, 'user', 'group')
    self.mox.ReplayAll()

    self.args.base_dir = BASE_DIR
    umpire.Init(self.args)


class UpdateTest(unittest.TestCase):
  FIRMWARE_PATH = os.path.join(TESTDATA_DIR, 'firmware.gz')
  TOOLKIT_PATH = os.path.join(TESTDATA_DIR, 'install_factory_toolkit.run')

  def setUp(self):
    self.args = Obj(source_id=None, dest_id=None, resources=list())
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testUpdateSingleResource(self):
    # Expect XMLRPC call.
    self.mock_cli.Update([('factory_toolkit', self.TOOLKIT_PATH)], None, None)
    self.mox.ReplayAll()

    self.args.resources.append('factory_toolkit=%s' % self.TOOLKIT_PATH)
    umpire.Update(self.args, self.mock_cli)
    self.assertListEqual(
        ['Updating resources of default bundle in place',
         'Updating resources:',
         '  factory_toolkit  %s' % self.TOOLKIT_PATH,
         'Update successfully.', ''],
        GetStdout())

  def testUpdateSingleResourceWithSourceDestId(self):
    # Expect XMLRPC call.
    self.mock_cli.Update([('factory_toolkit', self.TOOLKIT_PATH)], 'bundle1',
                         'bundle2')
    self.mox.ReplayAll()

    self.args.resources.append('factory_toolkit=%s' % self.TOOLKIT_PATH)
    self.args.source_id = 'bundle1'
    self.args.dest_id = 'bundle2'
    umpire.Update(self.args, self.mock_cli)
    self.assertListEqual(
        ["Creating a new bundle 'bundle2' based on bundle 'bundle1' with new "
         'resources',
         'Updating resources:',
         '  factory_toolkit  %s' % self.TOOLKIT_PATH,
         'Update successfully.', ''],
        GetStdout())

  def testUpdateMultipleResources(self):
    # Expect XMLRPC call.
    self.mock_cli.Update([('factory_toolkit', self.TOOLKIT_PATH),
                          ('firmware', self.FIRMWARE_PATH)], None, None)
    self.mox.ReplayAll()

    self.args.resources.append('factory_toolkit=%s' % self.TOOLKIT_PATH)
    self.args.resources.append('firmware=%s' % self.FIRMWARE_PATH)
    umpire.Update(self.args, self.mock_cli)
    self.assertListEqual(
        ['Updating resources of default bundle in place',
         'Updating resources:',
         '  factory_toolkit  %s' % self.TOOLKIT_PATH,
         '  firmware  %s' % self.FIRMWARE_PATH,
         'Update successfully.', ''],
        GetStdout())

  def testUpdateInvalidResourceType(self):
    self.mox.ReplayAll()

    self.args.resources.append('wrong_res_type=%s' % self.TOOLKIT_PATH)
    self.assertRaisesRegexp(UmpireError, 'Unsupported resource type',
                            umpire.Update, self.args, self.mock_cli)

  def testUpdateInvalidResourceFile(self):
    self.mox.ReplayAll()

    self.args.resources.append('fsi=/path/to/nowhere')
    self.assertRaisesRegexp(IOError, 'Resource file not found',
                            umpire.Update, self.args, self.mock_cli)


class ImportBundleTest(unittest.TestCase):
  BUNDLE_PATH = os.path.join(TESTDATA_DIR, 'init_bundle')

  def setUp(self):
    self.args = Obj(id=None, bundle_path='.', note=None)
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testImportBundle(self):
    # Expect XMLRPC call.
    self.mock_cli.ImportBundle(
        self.BUNDLE_PATH, 'new_bundle', 'new bundle').AndReturn(
            'umpire.yaml##00000000')

    self.mox.ReplayAll()

    self.args.bundle_path = self.BUNDLE_PATH
    self.args.id = 'new_bundle'
    self.args.note = 'new bundle'

    umpire.ImportBundle(self.args, self.mock_cli)
    self.assertListEqual(
        ['Importing bundle %r with specified bundle ID %r' % (
            self.BUNDLE_PATH, 'new_bundle'),
         "Import bundle successfully. Staging config 'umpire.yaml##00000000'",
         ''],
        GetStdout())


class ImportResourceTest(unittest.TestCase):
  BUNDLE_PATH = os.path.join(TESTDATA_DIR, 'init_bundle')

  def setUp(self):
    self.args = Obj(resources=[])
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

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
      umpire.ImportResource(self.args, self.mock_cli)


class DeployTest(unittest.TestCase):
  ACTIVE_CONFIG_PATH = os.path.join(
      TESTDATA_DIR, 'minimal_empty_services_with_enable_update_umpire.yaml')
  STAGING_CONFIG_PATH = os.path.join(TESTDATA_DIR, 'minimal_umpire.yaml')

  def setUp(self):
    self.args = Obj()
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testDeployNoStaging(self):
    self.mock_cli.GetStatus().AndReturn({'staging_config': ''})
    self.mox.ReplayAll()

    self.assertRaisesRegexp(UmpireError, 'no staging file',
                            umpire.Deploy, self.args, self.mock_cli)

  def testDeploy(self):
    active_config = open(self.ACTIVE_CONFIG_PATH).read()
    staging_config = open(self.STAGING_CONFIG_PATH).read()
    self.mox.StubOutWithMock(__builtin__, 'raw_input')

    self.mock_cli.GetStatus().AndReturn(
        {'staging_config': staging_config,
         'staging_config_res': 'mock_staging##00000000',
         'active_config': active_config})
    self.mock_cli.ValidateConfig(staging_config)
    raw_input('Ok to deploy [y/n]? ').AndReturn('Y')
    self.mock_cli.Deploy('mock_staging##00000000')
    self.mox.ReplayAll()

    umpire.Deploy(self.args, self.mock_cli)
    self.assertListEqual(
        ['Getting status...',
         'Validating staging config for deployment...',
         'Changes for this deploy: ', '',
         "Deploying config 'mock_staging##00000000'",
         'Deploy successfully.', ''],
        GetStdout())

  def testDeployUserSayNo(self):
    active_config = open(self.ACTIVE_CONFIG_PATH).read()
    staging_config = open(self.STAGING_CONFIG_PATH).read()
    self.mox.StubOutWithMock(__builtin__, 'raw_input')

    self.mock_cli.GetStatus().AndReturn(
        {'staging_config': staging_config,
         'staging_config_res': 'mock_staging##00000000',
         'active_config': active_config})
    self.mock_cli.ValidateConfig(staging_config)
    raw_input('Ok to deploy [y/n]? ').AndReturn('x')
    # No mock.cli.Deploy is called
    self.mox.ReplayAll()

    umpire.Deploy(self.args, self.mock_cli)
    self.assertListEqual(['Getting status...',
                          'Validating staging config for deployment...',
                          'Changes for this deploy: ', '',
                          'Abort by user.', ''],
                         GetStdout())


if __name__ == '__main__':
  unittest.main(buffer=True)
