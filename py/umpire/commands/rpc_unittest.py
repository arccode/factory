#!/usr/bin/env trial
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

import mox
from twisted.internet import defer, reactor
from twisted.python import failure
from twisted.trial import unittest
from twisted.web import server, xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import utils
from cros.factory.umpire.commands import rpc
from cros.factory.umpire.commands import update
from cros.factory.umpire.common import UMPIRE_COMMAND_PORT, UmpireError
from cros.factory.umpire.umpire_env import UmpireEnv


class MockUmpireDaemon(object):
  def __init__(self):
    self.Deploy = None
    self.Stop = None
    reg = utils.Registry()
    reg.setdefault('active_config_file', None)


class CommandTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    reg = utils.Registry()
    reg.umpired = MockUmpireDaemon()
    self.proxy = xmlrpc.Proxy('http://localhost:%d' % UMPIRE_COMMAND_PORT)
    self.rpc_command = rpc.UmpireCommand()
    self.port = reactor.listenTCP(UMPIRE_COMMAND_PORT,
                                  server.Site(self.rpc_command))

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    return self.port.stopListening()

  def Call(self, function, *args):
    return self.proxy.callRemote(function, *args)

  def AssertSuccess(self, deferred):
    deferred.addErrback(lambda _: self.fail('Expect successful RPC'))
    return deferred

  def AssertFailure(self, deferred):
    def Errback(result):
      self.assertTrue(result, failure.Failure)
      return 'OK'

    deferred.addCallbacks(
        lambda _: self.fail('Expect failed RPC'),
        Errback)
    return deferred

  def testDeploy(self):
    reg = utils.Registry()
    # Deploy callback
    reg.umpired.Deploy = lambda _: defer.succeed('OK')
    return self.AssertSuccess(self.Call('deploy', 'foo.yaml'))

  def testDeployFailure(self):
    reg = utils.Registry()
    reg.umpired.Deploy = lambda _: defer.fail(UmpireError('ERROR'))
    return self.AssertFailure(self.Call('deploy', 'ERROR'))

  def testStop(self):
    reg = utils.Registry()
    reg.umpired.Stop = lambda: defer.succeed('OK')
    return self.AssertSuccess(self.Call('stop'))

  def testStopFailure(self):
    reg = utils.Registry()
    reg.umpired.Stop = lambda: defer.fail(UmpireError('ERROR'))
    return self.AssertFailure(self.Call('stop'))

  def testUpdate(self):
    utils.Registry().env = UmpireEnv()

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

    d = self.Call('update', resource_to_update, 'sid', 'did')
    d.addCallback(lambda r: self.assertEqual(updated_config, r))
    return self.AssertSuccess(d)

  def testUpdateFailure(self):
    utils.Registry().env = UmpireEnv()

    resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]

    self.mox.StubOutClassWithMocks(update, 'ResourceUpdater')
    mock_updater = update.ResourceUpdater(mox.IsA(UmpireEnv))
    mock_updater.Update(resource_to_update, 'sid', 'did').AndRaise(
        UmpireError('mock error'))
    self.mox.ReplayAll()

    return self.AssertFailure(self.Call('update', resource_to_update, 'sid',
                                        'did'))
