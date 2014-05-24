#!/usr/bin/trial --temp-directory=/tmp/_trial_temp/
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

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
from cros.factory.umpire.rpc_cli import CLICommand
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.umpire.web.xmlrpc import XMLRPCContainer
from cros.factory.utils import net_utils


class CommandTest(unittest.TestCase):

  def setUp(self):
    test_port = net_utils.GetUnusedPort()
    self.env = UmpireEnv()
    self.mox = mox.Mox()
    self.proxy = xmlrpc.Proxy('http://localhost:%d' % test_port)
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
    def UnexpectedCallback(dummy_result):
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


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
