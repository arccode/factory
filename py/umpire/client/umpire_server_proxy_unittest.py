#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for UmpireServerProxy."""


import glob
import logging
import mox
import multiprocessing
import os
import re
import shutil
import signal
import socket
import SocketServer
import tempfile
import time
import unittest
from SimpleHTTPServer import SimpleHTTPRequestHandler
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

import factory_common  # pylint: disable=W0611
from cros.factory.test.utils import kill_process_tree
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.utils.file_utils import ForceSymlink, Read
from cros.factory.utils.net_utils import FindConsecutiveUnusedPorts

MOCK_UMPIRE_ADDR = 'http://localhost'
SEARCH_STARTING_PORT = 49998
TESTDATA_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), 'testdata')
UMPIRE_HANDLER_METHOD = 'umpire_handler_method'
UMPIRE_HANDLER_METHODS = [UMPIRE_HANDLER_METHOD]
SHOPFLOOR_HANDLER_METHOD = 'shopfloor_handler_method'

# Allow reuse address to prevent "[Errno 98] Address already in use."
SocketServer.TCPServer.allow_reuse_address = True

class ResourceMapWrapper(object):
  """Class to change which resourcemap http server should provide."""
  def __init__(self):
    self.resourcemap_path = None
  def SetPath(self, path):
    os.chdir(TESTDATA_DIRECTORY)
    logging.debug('Setting resourcemap link to %s', path)
    ForceSymlink(path, 'resourcemap')
    self.resourcemap_path = path

  def GetPath(self):
    return self.resourcemap_path


class MockUmpireHTTPHandler(SimpleHTTPRequestHandler):
  """Class to mock Umpire http handler."""
  def __init__(self, *args, **kwargs):
    SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

  def do_GET(self):
    """extends do_GET to check request header and path."""
    logging.debug('MockUmpireHTTPHandler receive do_GET for %s', self.path)
    assert self.path == '/resourcemap'
    logging.debug('Headers contains %r', self.headers.keys())
    assert 'x-umpire-dut' in self.headers.keys()
    info = self.headers['x-umpire-dut']
    logging.debug('Header contains dut info %r', info)
    SimpleHTTPRequestHandler.do_GET(self)


def RunServer(server):
  """Runs server forever until getting interrupt."""
  try:
    server.serve_forever()
  except Exception as e:
    if 'Interrupted system call' in str(e):
      logging.debug('Got interrupted. Just return.')
      return


master_pid = os.getpid()


def SignalHandler(signum, unused_frame):
  """Signal handler for master process."""
  logging.debug('got signal %d on pid %d', signum, os.getpid())
  if os.getpid() != master_pid:
    return
  UmpireServerProxyTest.StopAllServers()

signal.signal(signal.SIGINT, SignalHandler)
signal.signal(signal.SIGTERM, SignalHandler)


class MyXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
  """Mock xmlrpc request handler."""
  handler_name = None
  def do_POST(self):
    """Extends do_POST to generate error code and message."""
    os.chdir(TESTDATA_DIRECTORY)
    error_file = 'error_%s' % self.handler_name
    if os.path.exists(error_file):
      error_code, error_message = Read(error_file).split(' ', 1)
      logging.info('Generate an error %s, %s for handler %s',
                   error_code, error_message, self.handler_name)
      if int(error_code) == 410 and error_message == 'Gone':
        self.report_410()
        return
      if int(error_code) == 111 and error_message == 'Connectin refused':
        self.report_111()
        return
      else:
        raise Exception('Unknown error: %d, %s' % (
            int(error_code), error_message))
    else:
      SimpleXMLRPCRequestHandler.do_POST(self)

  def report_410(self):
    """Responses with a 410 error."""
    self.send_response(410)
    response = 'Gone'
    self.send_header("Content-type", "text/plain")
    self.send_header("Content-length", str(len(response)))
    self.end_headers()
    self.wfile.write(response)

  def report_111(self):
    """Responses with a 410 error."""
    self.send_response(111)
    response = 'Connection refused'
    self.send_header("Content-type", "text/plain")
    self.send_header("Content-length", str(len(response)))
    self.end_headers()
    self.wfile.write(response)

def MyXMLRPCRequestHandlerWrapper(name):
  """Wrapper for user to set handler_name in MyXMLRPCRequestHandler."""
  class HandlerWithName(MyXMLRPCRequestHandler):
    """MyXMLRPCRequestHandler with different handler_name"""
    handler_name = name
  return HandlerWithName

def HandlerFunctionWrapper(handler_name, use_umpire=False):
  """Wrapper for user to set handler_name in HandlerFunction."""
  def HandlerFunction(message):
    """An ordinary shop floor handler function."""
    logging.debug('Shop floor handler gets message: %s', message)
    return 'Handler: %s; message: %s' % (handler_name, message)
  # pylint: disable=W0613
  def UmpireHandlerFunction(message):
    """Umpire handler function"""
    logging.debug('Umpire handler gets message: %s', message)
    return 'Handler: %s; message: %s' % (handler_name, message)
  return UmpireHandlerFunction if use_umpire else HandlerFunction

def PingOfUmpire():
  """Ping method served on Umpire base XMLRPC handler."""
  return {'version': 3}

def PingOfShopFloor():
  """Ping method served on shop floor XMLRPC handler."""
  return True

def LongBusyMethod():
  """A long busy method"""
  logging.debug('Starting busy work')
  time.sleep(10)
  logging.warning('Ended busy work')
  return True

def SetHandlerError(handler_name, code, message):
  """Triggers specified error for handler.

  Writes a file 'error_<handler_name>' to testdata directory.
  The content of the file is error code and error message.
  Handler with that handler_name will check the file and generate the specified
  error.

  Args:
    handler_name:
    code:
    message:
  """
  logging.debug('Setting handler %s error: %d, %s',
                handler_name, code, message)
  os.chdir(TESTDATA_DIRECTORY)
  error_file = 'error_%s' % handler_name
  with open(error_file, 'w') as f:
    f.write('%d %s' % (code, message))

class UmpireServerProxyTest(unittest.TestCase):
  """Tests UmpireServerProxy.

  Properties:
    These are all class properties that will be used across tests.
    umpire_http_server: Umpire http server, which will handler resource map
      request.
    umpire_handler: Umpire xmlrpc handler, which will handle method call in
      UMPIRE_HANDLER_METHODS.
    shopfloor_handler_1: Shopfloor handler 1. Resourcemap 1 assigns this
      shopfloor to DUT.
    shopfloor_handler_2: Shopfloor handler 2. Resourcemap 2 assigns this
      shopfloor to DUT.
    umpire_http_server_process: Process for Umpire http server.
    umpire_base_handler_process: Process for Umpire base xmlrpc handler.
    umpire_handler_process: Process for Umpire xmlrpc handler.
    shopfloor_handler_1_process: Process for shopfloor handler 1.
    shopfloor_handler_2_process: Process for shopfloor handler 2.
    mock_resourcemap: A ResourceMapWrapper object to control which resourcemap
      Umpire http server should serve.
    modified_files: A list of file paths that have been modified. They need
      to be restored from .backup files in the end of the test.
  """
  umpire_http_server = None
  umpire_base_handler = None
  umpire_handler = None
  shopfloor_handler_1 = None
  shopfloor_handler_2 = None

  umpire_http_server_process = None
  umpire_base_handler_process = None
  umpire_handler_process = None
  shopfloor_handler_1_process = None
  shopfloor_handler_2_process = None

  UMPIRE_BASE_HANDLER_PORT = None
  UMPIRE_HTTP_SERVER_PORT = None
  UMPIRE_HANDLER_PORT = None
  SHOPFLOOR_1_PORT = None
  SHOPFLOOR_2_PORT = None
  NUMBER_OF_PORTS = 5
  UMPIRE_SERVER_URI = None
  SHOPFLOOR_SERVER_URI = None

  mock_resourcemap = ResourceMapWrapper()
  modified_files = []

  @classmethod
  def setUpClass(cls):
    """Starts servers before running any test of this class."""
    port = FindConsecutiveUnusedPorts(SEARCH_STARTING_PORT, cls.NUMBER_OF_PORTS)
    logging.debug('Set starting testing port to %r', port)
    cls.SetTestingPort(port)
    cls.SetupServers()

  @classmethod
  def ModifyShopFloorPortInResourceMap(cls, file_name, port):
    """Modify shop_floor_handler port in resourcemap.

    Args:
      file_name: Name of the resource map
      port: The port that should be overwritten to resourcemap.
    """
    file_path = os.path.join(TESTDATA_DIRECTORY, file_name)
    backup_file_path = file_path + '.backup'
    shutil.copyfile(file_path, backup_file_path)
    lines_to_write = []
    for line in open(file_path).readlines():
      line = re.sub(
          'shop_floor_handler: /shop_floor/(\d+)',
          'shop_floor_handler: /shop_floor/%d' % port,
          line)
      lines_to_write.append(line)
    _, temp_path = tempfile.mkstemp(prefix='umpire_server_proxy', dir='/tmp')
    with open(temp_path, 'w') as f:
      f.write(''.join(lines_to_write))
    shutil.move(temp_path, file_path)
    logging.debug('Modified content: %r in %r',
                  ''.join(lines_to_write), file_path)
    cls.modified_files.append(file_path)

  @classmethod
  def RestoreBackupFile(cls):
    """Restores backup files."""
    for file_path in cls.modified_files:
      shutil.move(file_path + '.backup', file_path)

  @classmethod
  def SetTestingPort(cls, umpire_base_handler_port):
    """Sets testing port based on umpire_base_handler_port"""
    cls.UMPIRE_BASE_HANDLER_PORT = umpire_base_handler_port
    cls.UMPIRE_HTTP_SERVER_PORT = umpire_base_handler_port + 1
    cls.UMPIRE_HANDLER_PORT = umpire_base_handler_port + 2
    cls.SHOPFLOOR_1_PORT = umpire_base_handler_port + 3
    cls.SHOPFLOOR_2_PORT = umpire_base_handler_port + 4
    cls.UMPIRE_SERVER_URI = '%s:%d' % (MOCK_UMPIRE_ADDR,
                                       cls.UMPIRE_BASE_HANDLER_PORT)
    cls.SHOPFLOOR_SERVER_URI = '%s:%d' % (MOCK_UMPIRE_ADDR,
                                          cls.SHOPFLOOR_1_PORT)
    cls.ModifyShopFloorPortInResourceMap('resourcemap1', cls.SHOPFLOOR_1_PORT)
    cls.ModifyShopFloorPortInResourceMap('resourcemap2', cls.SHOPFLOOR_2_PORT)

  @classmethod
  def tearDownClass(cls):
    """Stops servers in after running all test in this class."""
    cls.StopAllServers()
    cls.RestoreBackupFile()

  @classmethod
  def SetupServers(cls):
    """Setups http server and xmlrpc handlers."""
    cls.SetupHTTPServer()
    cls.SetupHandlers()

  @classmethod
  def StopAllServers(cls):
    """Terminates processes for servers if they are still alive."""
    if cls.umpire_http_server_process.is_alive():
      kill_process_tree(cls.umpire_http_server_process, 'umpire_http_server')
    if cls.umpire_handler_process.is_alive():
      kill_process_tree(cls.umpire_handler_process, 'umpire_handler')
    if cls.umpire_base_handler_process.is_alive():
      kill_process_tree(cls.umpire_base_handler_process, 'base_handler')
    if cls.shopfloor_handler_1_process.is_alive():
      kill_process_tree(cls.shopfloor_handler_1_process, 'shopfloor_handler_1')
    if cls.shopfloor_handler_2_process.is_alive():
      kill_process_tree(cls.shopfloor_handler_2_process, 'shopfloor_handler_1')
    cls.umpire_http_server_process.join()
    cls.umpire_handler_process.join()
    cls.umpire_base_handler_process.join()
    cls.shopfloor_handler_1_process.join()
    cls.shopfloor_handler_2_process.join()
    logging.debug('All servers stopped')

  @classmethod
  def SetupHTTPServer(cls):
    """Setups http server in its own process."""
    os.chdir(TESTDATA_DIRECTORY)
    logging.debug('Using UMPIRE_HTTP_SERVER_PORT: %r',
                  cls.UMPIRE_HTTP_SERVER_PORT)
    cls.umpire_http_server = SocketServer.TCPServer(
        ("", cls.UMPIRE_HTTP_SERVER_PORT), MockUmpireHTTPHandler)
    cls.umpire_http_server_process = multiprocessing.Process(
        target=RunServer, args=(cls.umpire_http_server,))
    cls.umpire_http_server_process.start()

  @classmethod
  def SetupHandlers(cls):
    """Setups xmlrpc servers and handlers in their own processes."""
    cls.umpire_base_handler = SimpleXMLRPCServer(
        addr=("", cls.UMPIRE_BASE_HANDLER_PORT),
        requestHandler=MyXMLRPCRequestHandlerWrapper('base_handler'),
        allow_none=True,
        logRequests=True)
    cls.umpire_base_handler.register_function(
        PingOfUmpire, 'Ping')
    cls.umpire_base_handler_process = multiprocessing.Process(
        target=RunServer, args=(cls.umpire_base_handler,))
    cls.umpire_base_handler_process.start()

    cls.umpire_handler = SimpleXMLRPCServer(
        ("", cls.UMPIRE_HANDLER_PORT),
        allow_none=True,
        logRequests=True)
    cls.umpire_handler.register_function(
        HandlerFunctionWrapper('umpire_handler', use_umpire=True),
        UMPIRE_HANDLER_METHOD)
    cls.umpire_handler.register_introspection_functions()
    cls.umpire_handler_process = multiprocessing.Process(
        target=RunServer, args=(cls.umpire_handler,))
    cls.umpire_handler_process.start()

    cls.shopfloor_handler_1 = SimpleXMLRPCServer(
        addr=("", cls.SHOPFLOOR_1_PORT),
        requestHandler=MyXMLRPCRequestHandlerWrapper('shopfloor_handler1'),
        allow_none=True,
        logRequests=True)
    cls.shopfloor_handler_1.register_function(
        HandlerFunctionWrapper('shopfloor_handler1'), SHOPFLOOR_HANDLER_METHOD)
    cls.shopfloor_handler_1.register_function(
        PingOfShopFloor, 'Ping')
    cls.shopfloor_handler_1.register_function(
        LongBusyMethod, 'LongBusyMethod')
    cls.shopfloor_handler_1_process = multiprocessing.Process(
        target=RunServer, args=(cls.shopfloor_handler_1,))
    cls.shopfloor_handler_1_process.start()

    cls.shopfloor_handler_2 = SimpleXMLRPCServer(
        ("", cls.SHOPFLOOR_2_PORT),
        requestHandler=MyXMLRPCRequestHandlerWrapper('shopfloor_handler2'),
        allow_none=True,
        logRequests=True)
    cls.shopfloor_handler_2.register_function(
        PingOfShopFloor, 'Ping')
    cls.shopfloor_handler_2.register_function(
        HandlerFunctionWrapper('shopfloor_handler2'), SHOPFLOOR_HANDLER_METHOD)
    cls.shopfloor_handler_2_process = multiprocessing.Process(
        target=RunServer, args=(cls.shopfloor_handler_2,))
    cls.shopfloor_handler_2_process.start()

  def setUp(self):
    """Setups mox and mock umpire_client_info used in tests."""
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(umpire_server_proxy, 'UmpireClientInfo')
    self.fake_umpire_client_info = self.mox.CreateMockAnything()

  def ClearErrorFiles(self):
    """Clears obsolete error tag files generated for previous tests."""
    os.chdir(TESTDATA_DIRECTORY)
    for p in glob.glob('error_*'):
      os.unlink(p)

  def tearDown(self):
    """Clean up for each test."""
    self.ClearErrorFiles()
    self.mox.UnsetStubs()

  def testGetResourceMapAndConnectToUmpireHandler(self):
    """Inits an UmpireServerProxy and connects to Umpire xmlrpc handler."""
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')
    self.fake_umpire_client_info.Update().AndReturn(False)

    self.mox.ReplayAll()

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')

    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)
    self.assertTrue(proxy.use_umpire)

    result = proxy.__getattr__(UMPIRE_HANDLER_METHOD)('hi Umpire')
    self.assertEqual(
        result,
        'Handler: %s; message: %s' % ('umpire_handler', 'hi Umpire'))

    self.mox.VerifyAll()
    logging.debug('Done')

  def testGetResourceMapAndConnectToShopFloorHandler1(self):
    """Inits an UmpireServerProxy and connects to shopfloor handler 1."""
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')
    self.fake_umpire_client_info.Update().AndReturn(False)

    self.mox.ReplayAll()

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')

    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)

    result = proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor 1')
    self.assertEqual(
        result,
        'Handler: %s; message: %s' % ('shopfloor_handler1', 'hi shopfloor 1'))

    self.mox.VerifyAll()
    logging.debug('Done')

  def testHandleClientInfoUpdate(self):
    """Proxy tries to make a call but client info is updated."""
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO1')
    # When proxy tries to call method, Umpire_client_info.Update() returns
    # True, so proxy needs to request resourse map again.
    self.fake_umpire_client_info.Update().AndReturn(True)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO2')


    self.mox.ReplayAll()

    # Http server serves resourcemap1 to DUT.
    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')

    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)

    # After proxy init, http server serves resourcemap2 to DUT.
    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap2')

    # Proxy thinks it is talking to shopfloor 1, but actually it will talk
    # to shopfloor 2 after requesing resource map.
    result = proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor 1')
    self.assertEqual(result,
        'Handler: %s; message: %s' % ('shopfloor_handler2', 'hi shopfloor 1'))
    # Token will be changed to the token in resourcemap2.
    self.assertEqual(proxy._token, '00000002')  # pylint: disable=W0212
    self.mox.VerifyAll()
    logging.debug('Done')

  def testHandleServerErrorMessageGone(self):
    """Proxy tries to make a call but server says token is invalid."""
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')
    self.fake_umpire_client_info.Update().AndReturn(False)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')

    self.mox.ReplayAll()

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')

    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap2')
    # Lets shopfloor handler 1 generate 410 Gone error.
    SetHandlerError('shopfloor_handler1', 410, 'Gone')
    # Proxy thinks it is talking to shopfloor 1, but actually it will talk
    # to shopfloor 2 after requesing resource map.
    result = proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor 1')
    # It talks to shopfloor_handler2 actually.
    self.assertEqual(
        result,
        'Handler: %s; message: %s' % ('shopfloor_handler2', 'hi shopfloor 1'))

    self.mox.VerifyAll()
    logging.debug('Done')

  def testHandleServerErrorMessageGoneRetriesFail(self):
    """Proxy tries to make a call but server always says token is invalid."""
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')
    self.fake_umpire_client_info.Update().AndReturn(False)
    for _ in xrange(5):
      self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')

    self.mox.ReplayAll()

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')

    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)

    # Lets shopfloor handler 1 generate 410 Gone error.
    SetHandlerError('shopfloor_handler1', 410, 'Gone')

    with self.assertRaises(umpire_server_proxy.UmpireServerProxyException):
      proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor 1')

    self.mox.VerifyAll()
    logging.debug('Done')

  def testHandleServerErrorMessageConnectionRefused(self):
    """Inits proxy but server is unavailable.

    Server version detection will be deferred to the time when method is
    invoked through proxy.
    """
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')
    self.fake_umpire_client_info.Update().AndReturn(False)

    self.mox.ReplayAll()

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')
    # Lets base handler generates 111 Connection refused error.
    # Proxy can not decide server version at its init time.
    SetHandlerError('base_handler', 111, 'Connection refused')

    # It is OK if server is not available at proxy init time.
    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)

    # It is not OK if server is not available when method is called though
    # proxy.
    with self.assertRaises(umpire_server_proxy.UmpireServerProxyException):
      proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor 1')

    # Clear error files so base handler will not return 111 error.
    self.ClearErrorFiles()

    # to shopfloor 1 after requesing resource map.
    result = proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor 1')
    # It talks to shopfloor_handler2 actually.
    self.assertEqual(
        result,
        'Handler: %s; message: %s' % ('shopfloor_handler1', 'hi shopfloor 1'))

    self.mox.VerifyAll()
    logging.debug('Done')

  def testNotUsingUmpire(self):
    """Proxy is working with ordinary shopfloor handler."""
    self.mox.ReplayAll()

    # Using test_mode=False so proxy will set handler port as the same port
    # it gets in __init__.
    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.SHOPFLOOR_SERVER_URI,
        test_mode=False)
    self.assertFalse(proxy.use_umpire)

    result = proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor')
    self.assertEqual(
        result,
        'Handler: %s; message: %s' % ('shopfloor_handler1', 'hi shopfloor'))

    self.mox.VerifyAll()
    logging.debug('Done')

  def testTimeoutUmpireServerProxy(self):
    """Proxy is working with ordinary shopfloor handler."""
    umpire_server_proxy.UmpireClientInfo().AndReturn(
        self.fake_umpire_client_info)
    self.fake_umpire_client_info.GetXUmpireDUT().AndReturn('MOCK_DUT_INFO')
    self.fake_umpire_client_info.Update().AndReturn(False)

    self.mox.ReplayAll()

    UmpireServerProxyTest.mock_resourcemap.SetPath('resourcemap1')

    # Uses TimeoutUmpireServerProxy with timeout set to 1.
    proxy = umpire_server_proxy.TimeoutUmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        timeout=1,
        test_mode=True)

    # Calls a long busy method will trigger a socket.error exception.
    # This is supported by TimeoutUmpireServerProxy.
    with self.assertRaises(socket.error):
      proxy.LongBusyMethod()

    self.mox.VerifyAll()
    logging.debug('Done')

  def testUseUmpireProperty(self):
    """Checks use_umpire property.

    Server version detection will be deferred to the time when method is
    invoked through proxy, or when use_umpire property is accessed by user.
    """
    # Lets base handler generates 111 Connection refused error.
    # Proxy can not decide server version at its init time.
    SetHandlerError('base_handler', 111, 'Connection refused')

    # It is OK if server is not available at proxy init time.
    proxy = umpire_server_proxy.UmpireServerProxy(
        server_uri=self.UMPIRE_SERVER_URI,
        test_mode=True)

    # It is not OK if server is not available when user wants to check
    # use_umpire property.
    with self.assertRaises(umpire_server_proxy.UmpireServerProxyException):
      _ = proxy.use_umpire

    # Clear error files so base handler will not return 111 error.
    self.ClearErrorFiles()

    # Server is reachable, so use_umpire is determined when this property is
    # accessed by user.
    self.assertTrue(proxy.use_umpire)

    logging.debug('Done')


if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s',
      level=logging.DEBUG)
  unittest.main()
