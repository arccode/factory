#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import logging
import os
import shutil

from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.trial import unittest
from twisted.web import client
from twisted.web import http_headers
from twisted.web import xmlrpc

from cros.factory.umpire import common
from cros.factory.umpire.server import daemon
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import umpire_rpc
from cros.factory.umpire.server import unittest_helper
from cros.factory.umpire.server.web import wsgi
from cros.factory.utils import net_utils
from cros.factory.utils import type_utils


# Forward to the correct executer with additional arguments.
if __name__ == '__main__':
  unittest_helper.ExecScriptWithTrial()


TESTDIR = os.path.abspath(os.path.join(os.path.split(__file__)[0], 'testdata'))
TESTCONFIG = os.path.join(TESTDIR, 'minimal_empty_services_umpire.json')


class _ReadContentProtocol(protocol.Protocol):

  def __init__(self, deferred):
    self.deferred = deferred
    self.buffers = []

  def dataReceived(self, data):
    self.buffers.append(data)

  def connectionLost(self, reason=protocol.connectionDone):
    if reason.check(client.ResponseDone):
      self.deferred.callback(b''.join(self.buffers))
    elif reason.check(client.PotentialDataLost):
      self.deferred.errback(common.UmpireError('Read content failed'))
    else:
      self.deferred.errback(reason)


def ReadContent(response):
  d = defer.Deferred()
  response.deliverBody(_ReadContentProtocol(d))
  return d


class TestWebApplication(wsgi.WebApp):

  def Handle(self, session):
    logging.debug('test webapp is called: %s', session)
    return session.Respond(
        '\n  - REQUEST_METHOD=%s\n  - remote_address=%s\n  - PATH_INFO=%s' %
        (session.REQUEST_METHOD, session.remote_address, session.PATH_INFO))


class TestCommand:

  @umpire_rpc.RPCCall
  def Add(self, param1, param2):
    return param1 + param2


class DaemonTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest(
        net_utils.FindUnusedPort(tcp_only=True, length=5))
    shutil.copy(TESTCONFIG, self.env.active_config_file)
    self.env.LoadConfig()
    self.daemon = daemon.UmpireDaemon(self.env)
    self.rpc_proxy = xmlrpc.Proxy(
        b'http://%s:%d' % (net_utils.LOCALHOST.encode('utf-8'),
                           self.env.umpire_cli_port))
    self.agent = client.Agent(reactor)

  def tearDown(self):
    for p in self.daemon.twisted_ports:
      p.stopListening()
    self.daemon.twisted_ports = []
    self.daemon = None
    self.rpc_proxy = None
    self.agent = None
    self.env.Close()

  def GET(self, path, session=None, headers=None):
    """Issues HTTP GET request.
    Response headers and body will be stored in AttrDict session.

    Args:
      session: AttrDict to store results of this request session.

    Returns:
      Deferred object.
    """
    if session is None:
      session = type_utils.AttrDict()
    url = b'http://%s:%d%s' % (net_utils.LOCALHOST.encode('utf-8'),
                               self.env.umpire_webapp_port,
                               path.encode('utf-8'))
    logging.debug('GET %s', url)
    if headers:
      headers = copy.deepcopy(headers)
    else:
      headers = {}
    headers.update({'User-Agent': ['Trial unittest']})
    headers = http_headers.Headers(headers)
    d = self.agent.request(b'GET', url, headers, None)
    d.addCallback(lambda response: self.OnResponse(session, response))
    return d

  def OnResponse(self, session, response):
    """Event handler for web user agent request.i

    Args:
      session: AttrDict to store results of this request session.

    Returns:
      Deferred object.
    """
    session.headers = list(response.headers.getAllRawHeaders())
    d = ReadContent(response)
    d.addCallback(lambda body: self.OnBody(session, body))
    return d

  def OnBody(self, session, body):
    session.body = body
    return session

  def testWebAppSite(self):
    def _Callback(result):
      logging.debug('test callback: %s', result)
      self.assertIn(b'REQUEST_METHOD=GET', result['body'])
      return result

    app = TestWebApplication()
    self.daemon.AddWebApp('/foobar', app)
    self.daemon.BuildWebAppSite()
    d = self.GET('/foobar')
    d.addCallback(_Callback)
    return d

  def testRPCSite(self):
    command = TestCommand()
    self.daemon.AddMethodForCLI(command)
    self.daemon.BuildRPCSite(
        self.env.umpire_cli_port,
        self.daemon.methods_for_cli)
    d = self.rpc_proxy.callRemote('Add', 'foo', 'bar')
    d.addCallback(lambda r: self.assertEqual('foobar', r))
    return d


if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  logging.disable(logging.CRITICAL)
