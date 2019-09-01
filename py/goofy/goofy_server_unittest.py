#!/usr/bin/env python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import time
import unittest
import urllib2

from jsonrpclib import jsonrpc

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy_server
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


class PathResolverTest(unittest.TestCase):

  def _Callback(self):
    pass

  def testWithRoot(self):
    resolver = goofy_server.PathResolver()
    resolver.AddPath('/', '/root')
    resolver.AddPath('/a/b', '/c/d')
    resolver.AddPath('/a', '/e')
    resolver.AddHandler('/callback', self._Callback)

    for url_path, expected in (
        ('/', '/root'),
        ('/a/b', '/c/d'),
        ('/a', '/e'),
        ('/a/b/X', '/c/d/X'),
        ('/a/X', '/e/X'),
        ('/X', '/root/X'),
        ('/X/', '/root/X/'),
        ('/X/Y', '/root/X/Y'),
        ('Blah', None),
        ('/callback', self._Callback)):
      self.assertEqual(expected,
                       resolver.Resolve(url_path))

  def testNoRoot(self):
    resolver = goofy_server.PathResolver()
    resolver.AddPath('/a/b', '/c/d')
    self.assertEqual(None, resolver.Resolve('/b'))
    self.assertEqual('/c/d/X', resolver.Resolve('/a/b/X'))

  def testRootHandler(self):
    resolver = goofy_server.PathResolver()
    resolver.AddHandler('/', self._Callback)
    resolver.AddPath('/a', '/e')

    self.assertEqual(resolver.Resolve('/'), self._Callback)
    self.assertEqual(resolver.Resolve('/a/b'), '/e/b')
    self.assertEqual(resolver.Resolve('/b'), None)


class GoofyServerTest(unittest.TestCase):

  def setUp(self):
    def ServerReady():
      try:
        urllib2.urlopen(
            'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, '/not_exists'))
      except urllib2.HTTPError as err:
        if err.code == 404:
          return True
      return False

    self.port = net_utils.FindUnusedTCPPort()
    self.server = goofy_server.GoofyServer(
        (net_utils.LOCALHOST, self.port))
    self.server_thread = process_utils.StartDaemonThread(
        target=self.server.serve_forever,
        args=(0.01,),
        name='GoofyServer')

    # Wait for server to start.
    sync_utils.WaitFor(ServerReady, 0.1)

  def testAddRPCInstance(self):
    class RPCInstance(object):
      def __init__(self):
        self.called = False

      def Func(self):
        self.called = True

    instance = RPCInstance()
    self.server.AddRPCInstance('/test', instance)

    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/test' % (net_utils.LOCALHOST, self.port))
    proxy.Func()
    self.assertTrue(instance.called)

  def testAddHTTPGetHandler(self):
    data = '<html><body><h1>Hello</h1></body></html>'
    mime_type = 'text/html'

    def MyHandler(handler):
      handler.send_response(200)
      handler.send_header('Content-Type', mime_type)
      handler.send_header('Content-Length', len(data))
      handler.end_headers()
      handler.wfile.write(data)

    self.server.AddHTTPGetHandler('/test', MyHandler)

    response = urllib2.urlopen(
        'http://%s:%d/test' % (net_utils.LOCALHOST, self.port))
    self.assertEqual(200, response.getcode())
    self.assertEqual(data, response.read())
    response.close()

  def testRegisterPath(self):
    data = '<html><body><h1>Hello</h1></body></html>'
    with file_utils.TempDirectory() as path:
      with open(os.path.join(path, 'index.html'), 'w') as f:
        f.write(data)

      self.server.RegisterPath('/', path)
      response = urllib2.urlopen(
          'http://%s:%d/' % (net_utils.LOCALHOST, self.port))
      self.assertEqual(200, response.getcode())
      self.assertEqual(data, response.read())
      response.close()

      # Check svg mime type
      with open(os.path.join(path, 'test.svg'), 'w') as f:
        f.write(data)
      response = urllib2.urlopen(
          'http://%s:%d/test.svg' % (net_utils.LOCALHOST, self.port))
      self.assertEqual(200, response.getcode())
      self.assertEqual(data, response.read())
      response.close()

  def testURLForData(self):
    data = '<html><body><h1>Hello</h1></body></html>'

    url = self.server.URLForData('text/html', data)

    response = urllib2.urlopen(
        'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))
    self.assertEqual(200, response.getcode())
    self.assertEqual(data, response.read())
    response.close()

  def testRegisterData(self):
    data = u'<html><body><h1>Hello</h1></body></html>'

    url = '/some/page.html'
    self.server.RegisterData(url, 'text/html', data)

    response = urllib2.urlopen(
        'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))
    self.assertEqual(200, response.getcode())
    self.assertEqual(data, response.read())
    response.close()

  def testRegisterDataUnicode(self):
    data = u'<html><body><h1>Hello\u4e16\u754c</h1></body></html>'

    url = '/some/page.html'
    self.server.RegisterData(url, 'text/html', data)

    response = urllib2.urlopen(
        'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))
    self.assertEqual(200, response.getcode())
    self.assertEqual(data, response.read().decode('UTF-8'))
    response.close()

  def testGoofyServerRPC(self):
    proxy = jsonrpc.ServerProxy(
        'http://%s:%d/' % (net_utils.LOCALHOST, self.port))
    self.assertItemsEqual(
        ['URLForData',
         'URLForFile',
         'RegisterPath',
         'system.listMethods',
         'system.methodHelp',
         'system.methodSignature'],
        proxy.system.listMethods())

    data = '<html><body><h1>Hello</h1></body></html>'
    url = proxy.URLForData('text/html', data)
    response = urllib2.urlopen(
        'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))
    self.assertEqual(200, response.getcode())
    self.assertEqual(data, response.read())
    response.close()

  def testURLForFile(self):
    data = '<html><body><h1>Hello</h1></body></html>'
    with file_utils.UnopenedTemporaryFile() as path:
      with open(path, 'w') as f:
        f.write(data)

      url = self.server.URLForFile(path)
      response = urllib2.urlopen(
          'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))
      self.assertEqual(200, response.getcode())
      self.assertEqual(data, response.read())
      response.close()

  def testURLForDataExpire(self):
    data = '<html><body><h1>Hello</h1></body></html>'

    url = self.server.URLForData('text/html', data, 0.8)

    response = urllib2.urlopen(
        'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))
    self.assertEqual(200, response.getcode())
    self.assertEqual(data, response.read())
    response.close()

    time.sleep(1)

    # The data should expired now.
    with self.assertRaises(urllib2.HTTPError):
      response = urllib2.urlopen(
          'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, url))

  def testURLNotFound(self):
    with self.assertRaisesRegexp(urllib2.HTTPError, '404: Not Found'):
      response = urllib2.urlopen(
          'http://%s:%d%s' % (net_utils.LOCALHOST, self.port, '/not_exists'))
      response.close()

  def tearDown(self):
    self.server.shutdown()
    self.server_thread.join()
    self.server.server_close()


if __name__ == '__main__':
  unittest.main()
