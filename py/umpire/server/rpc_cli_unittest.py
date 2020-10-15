#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=no-member

import logging
import os
import re
from unittest import mock

from twisted.internet import reactor
from twisted.trial import unittest
from twisted.web import server
from twisted.web import xmlrpc

from cros.factory.umpire import common
from cros.factory.umpire.server import daemon
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import rpc_cli
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import unittest_helper
from cros.factory.umpire.server.web import xmlrpc as umpire_xmlrpc
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils


# Forward to the correct executer with additional arguments.
if __name__ == '__main__':
  unittest_helper.ExecScriptWithTrial()


class CommandTest(unittest.TestCase):

  def setUp(self):
    self.test_port = net_utils.FindUnusedPort()
    self.env = umpire_env.UmpireEnvForTest()
    self.proxy = xmlrpc.Proxy(b'http://%s:%d' %
                              (net_utils.LOCALHOST.encode('utf-8'),
                               self.test_port))
    self.xmlrpc_resource = umpire_xmlrpc.XMLRPCContainer()
    self.umpire_cli = rpc_cli.CLICommand(daemon.UmpireDaemon(self.env))
    self.port = None

    def MockSuccess():
      return None

    def MockFailure():
      raise common.UmpireError('mock error')

    self.MockResultFunction = {
        True: MockSuccess,
        False: MockFailure
    }

  def tearDown(self):
    self.port.stopListening()
    self.env.Close()

  def SetUpMock(self, success, umpire_cli_func, *umpire_cli_func_args):
    def SideEffect(*args, **unused_kwargs):
      if args == umpire_cli_func_args:
        return self.MockResultFunction[success]()
      raise Exception('Wrong parameters')

    setattr(self.umpire_cli, umpire_cli_func, mock.Mock(
        getattr(self.umpire_cli, umpire_cli_func),
        side_effect=SideEffect,
        __name__=umpire_cli_func))

  def SetUpHandlerAndStartListen(self):
    self.xmlrpc_resource.AddHandler(self.umpire_cli)
    self.port = reactor.listenTCP(self.test_port,
                                  server.Site(self.xmlrpc_resource))

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
    resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]

    self.SetUpMock(True, 'Update', resource_to_update, 'sid', 'did')
    self.SetUpHandlerAndStartListen()

    d = self.Call('Update', resource_to_update, 'sid', 'did')
    return self.AssertSuccess(d)

  def testUpdateFailure(self):
    resource_to_update = [['factory_toolkit', '/tmp/factory_toolkit.tar.bz']]

    self.SetUpMock(False, 'Update', resource_to_update, 'sid', 'did')
    self.SetUpHandlerAndStartListen()

    return self.AssertFailure(
        self.Call('Update', resource_to_update, 'sid', 'did'),
        'UmpireError: mock error')

  def testImportBundle(self):
    bundle_path = '/path/to/bundle'
    bundle_id = 'test'
    note = 'test note'

    self.SetUpMock(True, 'ImportBundle', bundle_path, bundle_id, note)
    self.SetUpHandlerAndStartListen()

    return self.AssertSuccess(
        self.Call('ImportBundle', bundle_path, bundle_id, note))

  def testImportBundleFailure(self):
    bundle_path = '/path/to/bundle'
    bundle_id = 'test'
    note = 'test note'

    self.SetUpMock(False, 'ImportBundle', bundle_path, bundle_id, note)
    self.SetUpHandlerAndStartListen()

    return self.AssertFailure(
        self.Call('ImportBundle', bundle_path, bundle_id, note),
        'UmpireError: mock error')

  def testAddResourceResType(self):
    self.SetUpHandlerAndStartListen()

    checksum_for_empty = 'da39a3ee5e6b4b0d3255bfef95601890afd80709'

    file_to_add = os.path.join(self.env.base_dir, 'hwid')
    file_utils.WriteFile(file_to_add, 'checksum: %s' % checksum_for_empty)

    d = self.Call('AddPayload', file_to_add, resource.PayloadTypeNames.hwid)
    d.addCallback(lambda result: self.assertEqual(checksum_for_empty,
                                                  result['hwid']['version']))
    return self.AssertSuccess(d)

  def testAddConfigFail(self):
    self.SetUpHandlerAndStartListen()

    return self.AssertFailure(
        self.Call('AddConfig', '/path/to/nowhere',
                  resource.ConfigTypeNames.umpire_config),
        'FileNotFoundError:.*/path/to/nowhere')

  def testValidateConfig(self):
    config_str = 'umpire config'

    self.SetUpMock(True, 'ValidateConfig', config_str)
    self.SetUpHandlerAndStartListen()

    return self.AssertSuccess(self.Call('ValidateConfig', config_str))

  def testValidateConfigFailure(self):
    config_str = 'umpire config'

    self.SetUpMock(False, 'ValidateConfig', config_str)
    self.SetUpHandlerAndStartListen()

    return self.AssertFailure(self.Call('ValidateConfig', config_str),
                              'UmpireError: mock error')


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
