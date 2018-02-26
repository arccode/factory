#!/usr/bin/env python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import __builtin__  # Used for mocking raw_input().
import json
import os
import sys
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server import config
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import umpire
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


TESTDATA_DIR = os.path.realpath(os.path.join(
    os.path.dirname(__file__), 'testdata'))
DEFAULT_BUNDLE = os.path.join(TESTDATA_DIR, 'init_bundle')


def GetStdout():
  """Gets stdout buffer.

  Needs unittest.main(buffer=True).
  """
  # pylint: disable=no-member
  # getvalue is set when unittest.main has buffer=True arg.
  output = sys.stdout.getvalue()
  # pylint: enable=no-member
  return output.splitlines()


class UpdateTest(unittest.TestCase):
  FIRMWARE_PATH = os.path.join(TESTDATA_DIR, 'firmware.gz')
  TOOLKIT_PATH = os.path.join(TESTDATA_DIR, 'install_factory_toolkit.run')

  def setUp(self):
    self.args = type_utils.Obj(source_id=None, dest_id=None, resources=[])
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testUpdateSingleResource(self):
    # Expect XMLRPC call.
    self.mock_cli.Update([('toolkit', self.TOOLKIT_PATH)], None, None)
    self.mox.ReplayAll()

    self.args.resources.append('toolkit=%s' % self.TOOLKIT_PATH)
    umpire.Update(self.args, self.mock_cli)
    self.assertListEqual(
        ['Updating resources of default bundle in place',
         'Updating resources:',
         '  toolkit  %s' % self.TOOLKIT_PATH,
         'Update successfully.'],
        GetStdout())

  def testUpdateSingleResourceWithSourceDestId(self):
    # Expect XMLRPC call.
    self.mock_cli.Update([('toolkit', self.TOOLKIT_PATH)], 'bundle1',
                         'bundle2')
    self.mox.ReplayAll()

    self.args.resources.append('toolkit=%s' % self.TOOLKIT_PATH)
    self.args.source_id = 'bundle1'
    self.args.dest_id = 'bundle2'
    umpire.Update(self.args, self.mock_cli)
    self.assertListEqual(
        ["Creating a new bundle 'bundle2' based on bundle 'bundle1' with new "
         'resources',
         'Updating resources:',
         '  toolkit  %s' % self.TOOLKIT_PATH,
         'Update successfully.'],
        GetStdout())

  def testUpdateMultipleResources(self):
    # Expect XMLRPC call.
    self.mock_cli.Update([('toolkit', self.TOOLKIT_PATH),
                          ('firmware', self.FIRMWARE_PATH)], None, None)
    self.mox.ReplayAll()

    self.args.resources.append('toolkit=%s' % self.TOOLKIT_PATH)
    self.args.resources.append('firmware=%s' % self.FIRMWARE_PATH)
    umpire.Update(self.args, self.mock_cli)
    self.assertListEqual(
        ['Updating resources of default bundle in place',
         'Updating resources:',
         '  toolkit  %s' % self.TOOLKIT_PATH,
         '  firmware  %s' % self.FIRMWARE_PATH,
         'Update successfully.'],
        GetStdout())

  def testUpdateInvalidResourceType(self):
    self.mox.ReplayAll()

    self.args.resources.append('wrong_res_type=%s' % self.TOOLKIT_PATH)
    self.assertRaisesRegexp(common.UmpireError, 'Unsupported resource type',
                            umpire.Update, self.args, self.mock_cli)

  def testUpdateInvalidResourceFile(self):
    self.mox.ReplayAll()

    self.args.resources.append('release_image=/path/to/nowhere')
    self.assertRaisesRegexp(IOError, 'Missing resource',
                            umpire.Update, self.args, self.mock_cli)


class ImportBundleTest(unittest.TestCase):
  BUNDLE_PATH = os.path.join(TESTDATA_DIR, 'init_bundle')

  def setUp(self):
    self.args = type_utils.Obj(id=None, bundle_path='.', note=None)
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

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

    umpire.ImportBundle(self.args, self.mock_cli)
    self.assertListEqual(
        ['Importing bundle %r with specified bundle ID %r' % (
            self.BUNDLE_PATH, 'new_bundle'),
         "Import bundle successfully."],
        GetStdout())


class DeployTest(unittest.TestCase):
  ACTIVE_CONFIG_PATH = os.path.join(
      TESTDATA_DIR, 'minimal_empty_services_with_enable_update_umpire.json')
  NEW_CONFIG_PATH = os.path.join(TESTDATA_DIR, 'minimal_umpire.json')

  def setUp(self):
    self.args = type_utils.Obj()
    self.mox = mox.Mox()
    self.mock_cli = self.mox.CreateMockAnything()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testDeploy(self):
    active_config = file_utils.ReadFile(self.ACTIVE_CONFIG_PATH)
    new_config = file_utils.ReadFile(self.NEW_CONFIG_PATH)

    self.mox.StubOutWithMock(config, 'UmpireConfig')
    config.UmpireConfig(file_path='new_config').AndReturn(
        json.loads(new_config))
    config.UmpireConfig(active_config).AndReturn(json.loads(active_config))

    self.mox.StubOutWithMock(__builtin__, 'raw_input')
    raw_input('Ok to deploy [y/n]? ').AndReturn('Y')

    self.mock_cli.GetActiveConfig().AndReturn(active_config)
    self.mock_cli.AddConfig(
        'new_config',
        resource.ConfigTypeNames.umpire_config).AndReturn('umpire.123.json')
    self.mock_cli.Deploy('umpire.123.json')
    self.mox.ReplayAll()

    self.args.config_path = 'new_config'
    umpire.Deploy(self.args, self.mock_cli)
    self.assertListEqual(
        ["Validating config 'new_config' for deployment...",
         'Changes for this deploy: ', '',
         "Deploying config 'new_config'",
         'Deploy successfully.'],
        GetStdout())

  def testDeployUserSayNo(self):
    active_config = file_utils.ReadFile(self.ACTIVE_CONFIG_PATH)
    new_config = file_utils.ReadFile(self.NEW_CONFIG_PATH)

    self.mox.StubOutWithMock(config, 'UmpireConfig')
    config.UmpireConfig(file_path='new_config').AndReturn(
        json.loads(new_config))
    config.UmpireConfig(active_config).AndReturn(json.loads(active_config))

    self.mox.StubOutWithMock(__builtin__, 'raw_input')
    raw_input('Ok to deploy [y/n]? ').AndReturn('x')

    self.mock_cli.GetActiveConfig().AndReturn(active_config)
    # No mock.cli.Deploy is called
    self.mox.ReplayAll()

    self.args.config_path = 'new_config'
    umpire.Deploy(self.args, self.mock_cli)
    self.assertListEqual(
        ["Validating config 'new_config' for deployment...",
         'Changes for this deploy: ', '',
         'Abort by user.'],
        GetStdout())


if __name__ == '__main__':
  unittest.main(buffer=True)
