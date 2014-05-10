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
from cros.factory.umpire.commands import update
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.rpc_cli import CLICommand
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.umpire.web.xmlrpc import XMLRPCContainer


TEST_COMMAND_PORT = 8087


class CommandTest(unittest.TestCase):

  def setUp(self):
    self.env = UmpireEnv()
    self.mox = mox.Mox()
    self.proxy = xmlrpc.Proxy('http://localhost:%d' % TEST_COMMAND_PORT)
    xmlrpc_resource = XMLRPCContainer()
    umpire_cli = CLICommand(self.env)
    xmlrpc_resource.AddHandler(umpire_cli)
    self.port = reactor.listenTCP(TEST_COMMAND_PORT,
                                  server.Site(xmlrpc_resource))

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

if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
