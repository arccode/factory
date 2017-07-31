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
import re
from twisted.internet import reactor
from twisted.trial import unittest
from twisted.web import server
from twisted.web import xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire.server.commands import import_bundle
from cros.factory.umpire.server.commands import update
from cros.factory.umpire.server import config
from cros.factory.umpire.server import daemon
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import rpc_cli
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server.web import xmlrpc as umpire_xmlrpc
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils


class CommandTest(unittest.TestCase):

  def setUp(self):
    test_port = net_utils.FindUnusedPort()
    self.env = umpire_env.UmpireEnvForTest()
    self.mox = mox.Mox()
    self.proxy = xmlrpc.Proxy('http://%s:%d' % (net_utils.LOCALHOST, test_port))
    xmlrpc_resource = umpire_xmlrpc.XMLRPCContainer()
    umpire_cli = rpc_cli.CLICommand(daemon.UmpireDaemon(self.env))
    xmlrpc_resource.AddHandler(umpire_cli)
    self.port = reactor.listenTCP(test_port, server.Site(xmlrpc_resource))

  def tearDown(self):
    self.port.stopListening()
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    self.env.Close()

  def Call(self, function, *args):
    return self.proxy.callRemote(function, *args)

  def AssertSuccess(self, deferred):
    return deferred

  def AssertFailure(self, deferred, error_msg_re):
    def UnexpectedCallback(result):
      del result  # Unused.
      raise common.UmpireError('Expect failure')

    def ExpectedErrback(result):
      self.assertTrue(re.search(error_msg_re, result.getErrorMessage()))
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
    mock_updater = update.ResourceUpdater(mox.IsA(umpire_env.UmpireEnv))
    mock_updater.Update(resource_to_update, 'sid', 'did').AndReturn(
        updated_config)
    self.mox.ReplayAll()

    d = self.Call('Update', resource_to_update, 'sid', 'did')
    d.addCallback(lambda r: self.assertEqual(updated_config, r))
    return self.AssertSuccess(d)

  def testUpdateFailure(self):
    resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]

    self.mox.StubOutClassWithMocks(update, 'ResourceUpdater')
    mock_updater = update.ResourceUpdater(mox.IsA(umpire_env.UmpireEnv))
    mock_updater.Update(resource_to_update, 'sid', 'did').AndRaise(
        common.UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(
        self.Call('Update', resource_to_update, 'sid', 'did'),
        'UmpireError: mock error')

  def testImportBundle(self):
    bundle_path = '/path/to/bundle'
    bundle_id = 'test'
    note = 'test note'
    self.mox.StubOutWithMock(import_bundle, 'BundleImporter')
    mock_importer = self.mox.CreateMockAnything()
    import_bundle.BundleImporter(mox.IsA(umpire_env.UmpireEnv)).AndReturn(
        mock_importer)
    mock_importer.Import(bundle_path, bundle_id, note)
    self.mox.ReplayAll()

    return self.AssertSuccess(
        self.Call('ImportBundle', bundle_path, bundle_id, note))

  def testImportBundleFailure(self):
    bundle_path = '/path/to/bundle'
    bundle_id = 'test'
    note = 'test note'
    self.mox.StubOutWithMock(import_bundle, 'BundleImporter')
    mock_importer = self.mox.CreateMockAnything()
    import_bundle.BundleImporter(mox.IsA(umpire_env.UmpireEnv)).AndReturn(
        mock_importer)
    mock_importer.Import(bundle_path, bundle_id, note).AndRaise(
        common.UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(
        self.Call('ImportBundle', bundle_path, bundle_id, note),
        'UmpireError: mock error')

  def testAddResourceResType(self):
    checksum_for_empty = 'da39a3ee5e6b4b0d3255bfef95601890afd80709'

    file_to_add = os.path.join(self.env.base_dir, 'hwid')
    file_utils.WriteFile(file_to_add, 'checksum: %s' % checksum_for_empty)

    d = self.Call('AddPayload', file_to_add, resource.PayloadTypeNames.hwid)
    d.addCallback(lambda result: self.assertEqual(checksum_for_empty,
                                                  result['hwid']['version']))
    return self.AssertSuccess(d)

  def testAddConfigFail(self):
    return self.AssertFailure(
        self.Call('AddConfig', '/path/to/nowhere',
                  resource.ConfigTypeNames.umpire_config),
        'IOError:.*/path/to/nowhere')

  def testGetStagingConfig(self):
    # Prepare a staging config.
    active_config_path = os.path.join(self.env.base_dir, 'active_config')
    with file(active_config_path, 'w') as f:
      f.write('config\nfile')
    self.env.ActivateConfigFile(
        self.env.GetResourcePath(
            self.env.AddConfig(active_config_path,
                               resource.ConfigTypeNames.umpire_config)))
    self.env.StageConfigFile()

    d = self.Call('GetStagingConfig')
    d.addCallback(lambda result: self.assertEqual('config\nfile', result))
    return self.AssertSuccess(d)

  def testGetStagingConfigNotFound(self):
    # No staging config prepared.
    d = self.Call('GetStagingConfig')
    d.addCallback(self.assertIsNone)
    return self.AssertSuccess(d)

  def testStageConfigFile(self):
    # Prepare a file in resource to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    file_utils.WriteFile(config_to_stage, '...')

    config_to_stage_res_name = self.env.AddConfig(
        config_to_stage, resource.ConfigTypeNames.umpire_config)

    d = self.Call('StageConfigFile', config_to_stage_res_name)
    d.addCallback(
        lambda _: self.assertEqual(
            self.env.GetResourcePath(config_to_stage_res_name),
            os.path.realpath(self.env.staging_config_file)))
    return self.AssertSuccess(d)

  def testStageConfigFileDefaultActive(self):
    # Prepare active config.
    active_config_path = os.path.join(self.env.base_dir, 'active_config')
    file_utils.WriteFile(active_config_path, 'config\nfile')

    self.env.ActivateConfigFile(
        self.env.GetResourcePath(
            self.env.AddConfig(active_config_path,
                               resource.ConfigTypeNames.umpire_config)))

    d = self.Call('StageConfigFile')
    d.addCallback(
        lambda _: self.assertEqual(
            'config\nfile',
            file_utils.ReadFile(self.env.staging_config_file)))
    return self.AssertSuccess(d)

  def testStageConfigFileNotInResource(self):
    # Prepare a file not in resources to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    file_utils.WriteFile(config_to_stage, '...')

    d = self.Call('StageConfigFile', config_to_stage)
    d.addCallback(lambda _: self.assertRegexpMatches(
        os.path.realpath(self.env.staging_config_file),
        resource.GetResourceHashFromFile(config_to_stage)))
    return self.AssertSuccess(d)

  def testStageConfigFileFailFileAlreadyExists(self):
    # Prepare a file in resource to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    file_utils.WriteFile(config_to_stage, '...')

    config_to_stage_res_full_path = self.env.AddConfig(
        config_to_stage, resource.ConfigTypeNames.umpire_config)
    config_to_stage_res_name = os.path.basename(config_to_stage_res_full_path)

    # Set a stage config first.
    staged_config = os.path.join(self.env.base_dir, 'staged_config')
    file_utils.WriteFile(staged_config, 'staged...')

    self.env.StageConfigFile(staged_config)

    return self.AssertFailure(self.Call('StageConfigFile',
                                        config_to_stage_res_name),
                              'UmpireError:.*another config is already staged')

  def testStageConfigFileForce(self):
    # Prepare a file in resource to stage.
    config_to_stage = os.path.join(self.env.base_dir, 'config_to_stage')
    file_utils.WriteFile(config_to_stage, '...')

    config_to_stage_res_name = self.env.AddConfig(
        config_to_stage, resource.ConfigTypeNames.umpire_config)

    # Set a stage config first.
    staged_config = os.path.join(self.env.base_dir, 'staged_config')
    file_utils.WriteFile(staged_config, 'staged...')

    self.env.StageConfigFile(staged_config)

    # Force override current staging config file.
    d = self.Call('StageConfigFile', config_to_stage_res_name, True)
    d.addCallback(
        lambda _: self.assertEqual(
            self.env.GetResourcePath(config_to_stage_res_name),
            os.path.realpath(self.env.staging_config_file)))
    return self.AssertSuccess(d)

  def testUnstageConfigFile(self):
    # Prepare a file in resource and stage it.
    staged_config = os.path.join(self.env.base_dir, 'staged_config')
    file_utils.WriteFile(staged_config, 'staged...')

    self.env.StageConfigFile(staged_config)

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
        common.UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(self.Call('ValidateConfig', config_path),
                              'UmpireError: mock error')


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)