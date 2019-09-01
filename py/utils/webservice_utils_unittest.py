#!/usr/bin/env python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import jsonrpc_utils
from cros.factory.utils import net_utils
from cros.factory.utils import webservice_utils


class MockZeep(object):

  def __init__(self):
    self.service = None
    self.transports = self
    self.cache = self

  def InMemoryCache(self):
    return {}

  def Client(self):
    return self

  def Transport(self, cache=None):
    del cache  # Unused argument.
    return self


class WebServiceUtilsTest(unittest.TestCase):

  def setUp(self):
    self.port = net_utils.FindUnusedTCPPort()
    self.server = jsonrpc_utils.JSONRPCServer(
        port=self.port,
        methods={'GetDeviceInfo': self._GetDeviceInfo,
                 'JSONGetDeviceInfo': self._JSONGetDeviceInfo})
    self.url = 'http://%s:%d' % (net_utils.LOCALHOST, self.port)

  def _GetDeviceInfo(self, dict_arg):
    self.assertTrue(isinstance(dict_arg, dict))
    dict_arg["c"] = "d"
    return dict_arg

  def _JSONGetDeviceInfo(self, str_arg):
    self.assertTrue(isinstance(str_arg, basestring))
    return json.dumps(self._GetDeviceInfo(json.loads(str_arg)))

  def tearDown(self):
    self.server.Destroy()

  def testCheckPackage(self):
    f = webservice_utils.CheckPackage
    self.assertRaises(ImportError, lambda: f('', False, 'some package'))
    f('', True, 'some package')

  def testParseURL(self):
    url = 'http://192.168.0.1:8080'
    f = webservice_utils.ParseURL
    self.assertEqual(([], url), f(url))
    self.assertEqual((['json:'], url), f('json:' + url))
    self.assertEqual((['wsdl:'], url), f('wsdl:' + url))
    self.assertEqual((['xmlrpc:'], url), f('xmlrpc:' + url))
    self.assertEqual((['jsonrpc:'], url), f('jsonrpc:' + url))
    self.assertEqual((['json:', 'wsdl:'], url), f('json:wsdl:' + url))
    self.assertEqual(([], 'ssh:' + url), f('ssh:' + url))

  def testJSONRPCProxy(self):
    self.server.Start()
    param = {'a': 'b'}
    expected = {'a': 'b', 'c': 'd'}
    method1 = 'GetDeviceInfo'
    method2 = 'JSONGetDeviceInfo'
    f = webservice_utils.CreateWebServiceProxy

    proxy = f('jsonrpc:' + self.url)
    self.assertTrue(isinstance(proxy, webservice_utils.JSONRPCProxy))
    self.assertDictEqual(expected, proxy.callRemote(method1, param))
    self.assertDictEqual(expected, proxy.GetDeviceInfo(param))

    proxy = f('json:jsonrpc:' + self.url)
    self.assertTrue(isinstance(proxy, webservice_utils.JSONProxyFilter))
    self.assertDictEqual(expected, proxy.callRemote(method2, param))
    self.assertDictEqual(expected, proxy.JSONGetDeviceInfo(param))

    proxy = f('jsonrpc:json:' + self.url)
    self.assertTrue(isinstance(proxy, webservice_utils.JSONProxyFilter))
    self.assertDictEqual(expected, proxy.callRemote(method2, param))

    # If multiple protocols were assigned, creation would fail.
    self.assertRaises(ValueError, lambda: f('jsonrpc:wsdl:' + self.url))
    self.assertRaises(ValueError, lambda: f('jsonrpc:xmlrpc:' + self.url))
    self.assertRaises(ValueError, lambda: f('json:jsonrpc:xmlrpc:' + self.url))


    # Simulate 'zeep' to make sure WSDL is created properly.
    webservice_utils.zeep = MockZeep()
    webservice_utils.HAVE_ZEEP = True

    # Explicit WSDL
    self.assertTrue(isinstance(f('wsdl:' + self.url),
                               webservice_utils.ZeepProxy))
    self.assertTrue(isinstance(f(self.url + '?wsdl'),
                               webservice_utils.ZeepProxy))
    self.assertTrue(isinstance(f(self.url + '?WSDL'),
                               webservice_utils.ZeepProxy))

    # URLs ends with 'wsdl' won't be SOAP if explicit protocol was assigned.
    self.assertTrue(isinstance(f('jsonrpc:' + self.url + '?WSDL'),
                               webservice_utils.JSONRPCProxy))


if __name__ == '__main__':
  unittest.main()
