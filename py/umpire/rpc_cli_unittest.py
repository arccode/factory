#!/usr/bin/trial --temp-directory=/tmp/_trial_temp/
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

from __future__ import print_function

import logging
import mox
import os

from twisted.internet import reactor
from twisted.python import failure
from twisted.trial import unittest
from twisted.web import server, xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import import_bundle
from cros.factory.umpire.commands import update
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire import config
from cros.factory.umpire.rpc_cli import CLICommand
from cros.factory.umpire.umpire_env import UmpireEnv, UmpireEnvForTest
from cros.factory.umpire.web.xmlrpc import XMLRPCContainer
from cros.factory.utils import net_utils


class CommandTest(unittest.TestCase):

  def setUp(self):
    test_port = net_utils.GetUnusedPort()
    self.env = UmpireEnvForTest()
    self.mox = mox.Mox()
    self.proxy = xmlrpc.Proxy('http://%s:%d' % (net_utils.LOCALHOST, test_port))
    xmlrpc_resource = XMLRPCContainer()
    umpire_cli = CLICommand(self.env)
    xmlrpc_resource.AddHandler(umpire_cli)
    self.port = reactor.listenTCP(test_port, server.Site(xmlrpc_resource))

  def tearDown(self):
    self.port.stopListening()
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def Call(self, function, *args):
    return self.proxy.callRemote(function, *args)

  def AssertSuccess(self, deferred):
    return deferred

  def AssertFailure(self, deferred):
    def UnexpectedCallback(unused_result):
      raise UmpireError('Expect failure')

    def ExpectedErrback(result):
      self.assertTrue(result, failure.Failure)
      return 'OK'

    deferred.addCallbacks(UnexpectedCallback, ExpectedErrback)
    return deferred

  def testUpdate(self):
    # TODO(deanliao): figure out why proxy.callRemote converts [(a, b)] to
    #     [[a, b]].
    # resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]
    resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]
    updated_config = '/umpire/resources/config.yaml#12345678'

    self.mox.StubOutClassWithMocks(update, 'ResourceUpdater')
    mock_updater = update.ResourceUpdater(mox.IsA(UmpireEnv))
    mock_updater.Update(resource_to_update, 'sid', 'did').AndReturn(
        updated_config)
    self.mox.ReplayAll()

    d = self.Call('Update', resource_to_update, 'sid', 'did')
    d.addCallback(lambda r: self.assertEqual(updated_config, r))
    return self.AssertSuccess(d)

  def testUpdateFailure(self):
    resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]

    self.mox.StubOutClassWithMocks(update, 'ResourceUpdater')
    mock_updater = update.ResourceUpdater(mox.IsA(UmpireEnv))
    mock_updater.Update(resource_to_update, 'sid', 'did').AndRaise(
        UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(self.Call('Update', resource_to_update, 'sid',
                                        'did'))

  def testImportBundle(self):
    bundle_path = '/path/to/bundle'
    bundle_id = 'test'
    note = 'test note'
    self.mox.StubOutClassWithMocks(import_bundle, 'BundleImporter')
    mock_importer = import_bundle.BundleImporter(mox.IsA(UmpireEnv))
    mock_importer.Import(bundle_path, bundle_id, note)
    self.mox.ReplayAll()

    return self.AssertSuccess(self.Call('ImportBundle', bundle_path, bundle_id,
                                        note))

  def testImportBundleFailure(self):
    bundle_path = '/path/to/bundle'
    bundle_id = 'test'
    note = 'test note'
    self.mox.StubOutClassWithMocks(import_bundle, 'BundleImporter')
    mock_importer = import_bundle.BundleImporter(mox.IsA(UmpireEnv))
    mock_importer.Import(bundle_path, bundle_id, note).AndRaise(
        UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(self.Call('ImportBundle', bundle_path, bundle_id,
                                        note))

  def testAddResource(self):
    file_to_add = os.path.join(self.env.base_dir, 'file_to_add')
    with file(file_to_add, 'w') as f:
      f.write('...')
    expected_resource_name = 'file_to_add##2f43b42f'

    d = self.Call('AddResource', file_to_add)
    d.addCallback(lambda result: self.assertEqual(expected_resource_name,
                                                  result))
    return self.AssertSuccess(d)

  def testAddResourceResType(self):
    checksum_for_empty = 'da39a3ee5e6b4b0d3255bfef95601890afd80709'
    res_hash = '1f78df50'

    file_to_add = os.path.join(self.env.base_dir, 'hwid')
    with file(file_to_add, 'w') as f:
      f.write('checksum: %s' % checksum_for_empty)

    expected_resource_name = 'hwid#%s#%s' % (checksum_for_empty, res_hash)

    d = self.Call('AddResource', file_to_add, 'HWID')
    d.addCallback(lambda result: self.assertEqual(expected_resource_name,
                                                  result))
    return self.AssertSuccess(d)

  def testAddResourceFail(self):
    return self.AssertFailure(self.Call('AddResource', '/path/to/nowhere'))

  def testUploadConfig(self):
    basename = 'umpire.yaml'
    config_str = 'line1\nline2\nline3'

    def Verify(result):
      self.assertTrue(result.find(basename) != -1)
      with open(os.path.join(self.env.resources_dir, result)) as f:
        self.assertEqual(config_str, f.read())

    d = self.Call('UploadConfig', basename, config_str)
    d.addCallback(Verify)
    return self.AssertSuccess(d)

  def testGetStagingConfig(self):
    # Prepare a staging config.
    active_config_path = os.path.join(self.env.base_dir, 'active_config')
    with file(active_config_path, 'w') as f:
      f.write('config\nfile')
    self.env.ActivateConfigFile(self.env.AddResource(active_config_path))
    self.env.StageConfigFile()

    d = self.Call('GetStagingConfig')
    d.addCallback(lambda result: self.assertEqual('config\nfile', result))
    return self.AssertSuccess(d)

  def testGetStagingConfigNotFound(self):
    # No staging config prepared.
    d = self.Call('GetStagingConfig')
    d.addCallback(lambda result: self.assertEqual('', result))
    return self.AssertSuccess(d)

  def testStageConfigFile(self):
    # Prepare a file in resource to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    with file(config_to_stage, 'w') as f:
      f.write('...')
    config_to_stage_res_full_path = self.env.AddResource(config_to_stage)
    config_to_stage_res_name = os.path.basename(config_to_stage_res_full_path)

    d = self.Call('StageConfigFile', config_to_stage_res_name)
    d.addCallback(
        lambda _: self.assertEqual(
            config_to_stage_res_full_path,
            os.path.realpath(self.env.staging_config_file)))
    return self.AssertSuccess(d)

  def testStageConfigFileDefaultActive(self):
    # Prepare active config.
    active_config_path = os.path.join(self.env.base_dir, 'active_config')
    with file(active_config_path, 'w') as f:
      f.write('config\nfile')
    self.env.ActivateConfigFile(self.env.AddResource(active_config_path))

    # '': to stage active config.
    d = self.Call('StageConfigFile', '')
    d.addCallback(
        lambda _: self.assertEqual(
            'config\nfile',
            open(self.env.staging_config_file).read()))
    return self.AssertSuccess(d)

  def testStageConfigFileNotInResource(self):
    # Prepare a file not in resources to stage.
    res_basename = 'config_to_stage'
    config_to_stage = os.path.join(self.env.base_dir, res_basename)
    with file(config_to_stage, 'w') as f:
      f.write('...')

    d = self.Call('StageConfigFile', config_to_stage)
    d.addCallback(
        lambda _: self.assertRegexpMatches(
            os.path.realpath(self.env.staging_config_file), res_basename))
    return self.AssertSuccess(d)

  def testStageConfigFileFailFileAlreadyExists(self):
    # Prepare a file in resource to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    with file(config_to_stage, 'w') as f:
      f.write('...')
    config_to_stage_res_full_path = self.env.AddResource(config_to_stage)
    config_to_stage_res_name = os.path.basename(config_to_stage_res_full_path)

    # Set a stage config first.
    staged_config = os.path.join(self.env.base_dir, 'staged_config')
    with file(staged_config, 'w') as f:
      f.write('staged...')
    self.env.StageConfigFile(staged_config)

    return self.AssertFailure(self.Call('StageConfigFile',
                                        config_to_stage_res_name))

  def testStageConfigFileForce(self):
    # Prepare a file in resource to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    with file(config_to_stage, 'w') as f:
      f.write('...')
    config_to_stage_res_full_path = self.env.AddResource(config_to_stage)
    config_to_stage_res_name = os.path.basename(config_to_stage_res_full_path)

    # Set a stage config first.
    staged_config = os.path.join(self.env.base_dir, 'staged_config')
    with file(staged_config, 'w') as f:
      f.write('staged...')
    self.env.StageConfigFile(staged_config)

    # Force override current staging config file.
    d = self.Call('StageConfigFile', config_to_stage_res_name, True)
    d.addCallback(
        lambda _: self.assertEqual(
            config_to_stage_res_full_path,
            os.path.realpath(self.env.staging_config_file)))
    return self.AssertSuccess(d)

  def testUnstageConfigFile(self):
    # Prepare a file in resource and stage it.
    staged_config = os.path.join(self.env.base_dir, 'staged_config')
    with file(staged_config, 'w') as f:
      f.write('staged...')
    self.env.StageConfigFile(staged_config)

    # Force override current staging config file.
    self.assertTrue(self.env.HasStagingConfigFile())
    d = self.Call('UnstageConfigFile')
    d.addCallback(lambda _: self.assertFalse(self.env.HasStagingConfigFile()))
    return self.AssertSuccess(d)

  def testValidateConfig(self):
    config_path = '/path/to/config'
    self.mox.StubOutClassWithMocks(config, 'UmpireConfig')
    self.mox.StubOutWithMock(config, 'ValidateResources')
    mock_config = config.UmpireConfig(config_path)
    config.ValidateResources(mock_config, self.env)
    self.mox.ReplayAll()

    return self.AssertSuccess(self.Call('ValidateConfig', config_path))

  def testValidateConfigFailure(self):
    config_path = '/path/to/config'
    self.mox.StubOutClassWithMocks(config, 'UmpireConfig')
    self.mox.StubOutWithMock(config, 'ValidateResources')
    mock_config = config.UmpireConfig(config_path)
    config.ValidateResources(mock_config, self.env).AndRaise(
        UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(self.Call('ValidateConfig', config_path))


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
