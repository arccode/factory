#!/usr/bin/trial --temp-directory=/tmp/_trial_temp/
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

from __future__ import print_function

import copy
import logging
import os
import shutil
from twisted.internet import defer, reactor, protocol
from twisted.web import client, xmlrpc
from twisted.web.http_headers import Headers
from twisted.trial import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.common import AttrDict
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.daemon import UmpireDaemon
from cros.factory.umpire.umpire_env import UmpireEnvForTest
from cros.factory.umpire.umpire_rpc import RPCCall
from cros.factory.umpire.web.wsgi import WSGISession
from cros.factory.utils import net_utils


TESTDIR = os.path.abspath(os.path.join(os.path.split(__file__)[0], 'testdata'))
TESTCONFIG = os.path.join(TESTDIR, 'minimal_empty_services_umpire.yaml')


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
      self.deferred.errback(UmpireError('Read content failed'))
    else:
      self.deferred.errback(reason)


def ReadContent(response):
  d = defer.Deferred()
  response.deliverBody(_ReadContentProtocol(d))
  return d


class TestWebApplication(object):

  def __init__(self):
    super(TestWebApplication, self).__init__()
    self.session = None
    self.callback = None

  def GetPathInfo(self):
    return '/foobar'

  def __call__(self, environ, start_response):
    session = WSGISession(environ, start_response)
    self.session = session
    logging.debug('test webapp is called: %s', str(session))
    if callable(self.callback):
      return self.callback(self.session)  # pylint: disable=E1102
    return session.Response(
        '\n  - REQUEST_METHOD=%s\n  - remote_address=%s\n  - PATH_INFO=%s' %
        (session.REQUEST_METHOD, session.remote_address, session.PATH_INFO))

  def SetCallback(self, cb):
    self.callback = cb


class TestCommand(object):

  @RPCCall
  def Add(self, param1, param2):
    return param1 + param2


class DaemonTest(unittest.TestCase):

  def setUp(self):
    self.env = UmpireEnvForTest()
    shutil.copy(TESTCONFIG, self.env.active_config_file)
    self.env.LoadConfig()
    self.daemon = UmpireDaemon(self.env)
    self.rpc_proxy = xmlrpc.Proxy('http://%s:%d' %
        (net_utils.LOCALHOST, self.env.umpire_cli_port))
    self.agent = client.Agent(reactor)

  def tearDown(self):
    map(lambda p: p.stopListening(), self.daemon.twisted_ports)
    self.daemon.twisted_ports = []
    self.daemon = None
    self.rpc_proxy = None
    self.agent = None

  def GET(self, path, session=None, headers=None):
    """Issues HTTP GET request.
    Response headers and body will be stored in AttrDict session.

    Args:
      session: AttrDict to store results of this requst session.

    Returns:
      Deferred object.
    """
    if session is None:
      session = AttrDict()
    url = 'http://%s:%d%s' % (net_utils.LOCALHOST,
        self.env.umpire_webapp_port, path)
    logging.debug('GET %s', url)
    if headers:
      headers = copy.deepcopy(headers)
    else:
      headers = {}
    headers.update({'User-Agent': ['Trial unittest']})
    headers = Headers(headers)
    d = self.agent.request(
        'GET', url, headers, None)
    d.addCallback(lambda response: self.OnResponse(session, response))
    return d

  def OnResponse(self, session, response):
    """Event handler for web user agent request.i

    Args:
      session: AttrDict to store results of this requst session.

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
      logging.debug('test callback: %s', str(result))
      return result

    web_application = TestWebApplication()
    self.daemon.AddWebApp(web_application.GetPathInfo(), web_application)
    self.daemon.BuildWebAppSite()
    d = self.GET(web_application.GetPathInfo())
    d.addBoth(_Callback)
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
