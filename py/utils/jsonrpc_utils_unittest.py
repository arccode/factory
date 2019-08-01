#!/usr/bin/env python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSONRPC-related utilities."""

from __future__ import print_function

import socket
import SocketServer
import threading
import time
import unittest

import jsonrpclib
from jsonrpclib import jsonrpc
from jsonrpclib import SimpleJSONRPCServer

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import jsonrpc_utils
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class JSONRPCTest(unittest.TestCase):

  def setUp(self):
    self.port = net_utils.FindUnusedTCPPort()
    self.server = jsonrpc_utils.JSONRPCServer(
        port=self.port,
        methods={'Echo': self.echo,
                 'Sleep': self.sleep})
    self.simple_proxy = jsonrpclib.Server(
        'http://%s:%d' % (net_utils.LOCALHOST, self.port))
    self.timeout_proxy = jsonrpclib.Server(
        'http://%s:%d' % (net_utils.LOCALHOST, self.port),
        transport=jsonrpc_utils.TimeoutJSONRPCTransport(timeout=1))

  def tearDown(self):
    self.server.Destroy()

  def echo(self, s):
    return s

  def sleep(self, t):
    time.sleep(t)

  def testServer(self):
    self.server.Start()
    time.sleep(0.1)  # Wait for the server to start
    self.assertTrue(self.simple_proxy.IsAlive())
    self.assertEqual(self.simple_proxy.Echo('test'), 'test')

    # Check the UUID remains the same for the same server instance
    self.assertEqual(self.simple_proxy.GetUuid(), self.simple_proxy.GetUuid())

  def testTimeoutProxy(self):
    self.server.Start()

    start = time.time()
    self.timeout_proxy.Sleep(.001)  # No timeout
    delta = time.time() - start
    self.assertTrue(delta < 1, delta)

    start = time.time()
    try:
      self.timeout_proxy.Sleep(2)  # Cause a timeout in 1 s
      self.fail('Expected exception')
    except socket.timeout:
      delta = time.time() - start
      self.assertTrue(delta > .25, delta)
      self.assertTrue(delta < 2, delta)

    # Check the server is still alive
    self.assertEqual('alive', self.simple_proxy.Echo('alive'))


class MultiPathJSONRPCServerTest(unittest.TestCase):

  class MyServer(jsonrpc_utils.MultiPathJSONRPCServer,
                 SocketServer.ThreadingMixIn):
    pass


  class RPCInstance(object):
    def __init__(self):
      self.a_called = False
      self.b_called = False

    def A(self):
      self.a_called = True

    def B(self):
      self.b_called = True

    def Error(self):
      raise RuntimeError('Something Wrong')


  def setUp(self):
    def ServerReady():
      p = jsonrpc.ServerProxy(
          'http://%s:%d/' % (net_utils.LOCALHOST, self.port))
      try:
        p.Try()
      except jsonrpclib.ProtocolError as err:
        # We see 404 when the server is running instead of 111 (connection
        # refused)
        # ProtocolError has many different cases, and it may has a nested tuple.
        if 404 in type_utils.FlattenTuple(err.args):
          return True
      return False

    self.port = net_utils.FindUnusedTCPPort()
    self.server = self.MyServer((net_utils.LOCALHOST, self.port))
    self.server_thread = threading.Thread(
        target=self.server.serve_forever,
        name='MultiPathJSONRPCServer')
    self.server_thread.start()
    self.func_called = False

    sync_utils.WaitFor(ServerReady, 0.1)

  def Func(self):
    self.func_called = True

  def _SetInstance(self, url, instance):
    dispatcher = SimpleJSONRPCServer.SimpleJSONRPCDispatcher()
    dispatcher.register_introspection_functions()
    dispatcher.register_instance(instance)
    self.server.add_dispatcher(url, dispatcher)

  def testServer(self):
    def _CheckListMethods(methods, proxy):
      self.assertItemsEqual(
          methods + [u'system.listMethods',
                     u'system.methodHelp',
                     u'system.methodSignature'],
          proxy.system.listMethods())

    A = self.RPCInstance()
    B = self.RPCInstance()

    self._SetInstance('/', A)  # Check root path
    self._SetInstance('/B', B)

    dispatcher = SimpleJSONRPCServer.SimpleJSONRPCDispatcher()
    dispatcher.register_introspection_functions()
    dispatcher.register_function(self.Func)
    self.server.add_dispatcher('/C', dispatcher)

    # Check instance A
    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/' % (net_utils.LOCALHOST, self.port))
    _CheckListMethods([u'A', u'B', u'Error'], proxy)
    proxy.A()
    self.assertTrue(A.a_called)

    # Check instance B
    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/B' % (net_utils.LOCALHOST, self.port))
    _CheckListMethods([u'A', u'B', u'Error'], proxy)
    proxy.B()
    self.assertTrue(B.b_called)

    # Check instance C
    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/C' % (net_utils.LOCALHOST, self.port))
    _CheckListMethods([u'Func'], proxy)
    proxy.Func()
    self.assertTrue(self.func_called)

  def testURLNotFound(self):
    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/not_exists' % (net_utils.LOCALHOST, self.port))
    self.assertRaisesRegexp(
        jsonrpclib.ProtocolError, 'Not Found', proxy.Func)

  def testRPCException(self):
    self._SetInstance('/', self.RPCInstance())
    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/' % (net_utils.LOCALHOST, self.port))
    self.assertRaisesRegexp(
        jsonrpc.ProtocolError, 'RuntimeError: Something Wrong', proxy.Error)

  def tearDown(self):
    self.server.shutdown()
    self.server_thread.join()
    self.server.server_close()


if __name__ == '__main__':
  unittest.main()
