#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for UmpireServerProxy."""

from __future__ import print_function

import glob
import logging
import mox
import multiprocessing
import os
import shutil
import signal
import SimpleHTTPServer
import SimpleXMLRPCServer
import socket
import SocketServer
import tempfile
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.client import umpire_client
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.umpire import common
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils

MOCK_UMPIRE_ADDR = 'http://' + net_utils.LOCALHOST
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
    logging.debug('Setting resourcemap link to %s', path)
    file_utils.ForceSymlink(path, 'resourcemap')
    self.resourcemap_path = path

  def GetPath(self):
    return self.resourcemap_path


class MockUmpireHTTPHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
  """Class to mock Umpire http handler."""

  def __init__(self, *args, **kwargs):
    SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

  def do_GET(self):
    """extends do_GET to check request header and path."""
    logging.debug('MockUmpireHTTPHandler receive do_GET for %s', self.path)
    assert self.path == '/resourcemap'
    logging.debug('Headers contains %r', self.headers.keys())
    assert 'x-umpire-dut' in self.headers
    info = self.headers['x-umpire-dut']
    logging.debug('Header contains dut info %r', info)
    SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)


def RunServer(server):
  """Runs server forever until getting interrupt."""
  try:
    server.serve_forever()
  except Exception as e:
    if 'Interrupted system call' in str(e):
      logging.debug('Got interrupted. Just return.')
      return


master_pid = os.getpid()


def SignalHandler(signum, frame):
  """Signal handler for master process."""
  logging.debug('got signal %d on pid %d', signum, os.getpid())
  if os.getpid() == master_pid:
    UmpireServerProxyTest.StopAllServers()
  return original_handler[signum](signum, frame)

original_handler = {}
original_handler[signal.SIGINT] = signal.signal(signal.SIGINT, SignalHandler)
original_handler[signal.SIGTERM] = signal.signal(signal.SIGTERM, SignalHandler)


class MyXMLRPCRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
  """Mock xmlrpc request handler."""
  handler_name = None

  def do_POST(self):
    """Extends do_POST to generate error code and message."""
    error_file = 'error_%s' % self.handler_name
    if os.path.exists(error_file):
      error_code, error_message = file_utils.ReadFile(error_file).split(' ', 1)
      logging.info('Generate an error %s, %s for handler %s',
                   error_code, error_message, self.handler_name)
      if int(error_code) == 410 and error_message == 'Gone':
        self.report_410()
        return
      if int(error_code) == 111 and error_message == 'Connection refused':
        self.report_111()
        return
      else:
        raise Exception('Unknown error: %d, %s' % (
            int(error_code), error_message))
    else:
      SimpleXMLRPCServer.SimpleXMLRPCRequestHandler.do_POST(self)

  def report_410(self):
    """Responses with a 410 error."""
    self.send_response(410)
    response = 'Gone'
    self.send_header('Content-type', 'text/plain')
    self.send_header('Content-length', str(len(response)))
    self.end_headers()
    self.wfile.write(response)

  def report_111(self):
    """Responses with a 410 error."""
    self.send_response(111)
    response = 'Connection refused'
    self.send_header('Content-type', 'text/plain')
    self.send_header('Content-length', str(len(response)))
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
    """An ordinary XMLRPC handler function."""
    logging.debug('XMLRPC handler gets message: %s', message)
    return 'Handler: %s; message: %s' % (handler_name, message)

  def UmpireHandlerFunction(message):
    """Umpire handler function"""
    logging.debug('Umpire handler gets message: %s', message)
    return 'Handler: %s; message: %s' % (handler_name, message)
  return UmpireHandlerFunction if use_umpire else HandlerFunction


def PingOfUmpire():
  """Ping method served on Umpire base XMLRPC handler."""
  return {'version': common.UMPIRE_VERSION}


def PingOfLegacyServer():
  """Ping method served on legacy XMLRPC server handler."""
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
  logging.debug('Setting handler %s error: %d, %s', handler_name, code, message)
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
    umpire_http_server_process: Process for Umpire http server.
    umpire_base_handler_process: Process for Umpire base xmlrpc handler.
    umpire_handler_process: Process for Umpire xmlrpc handler.
    mock_resourcemap: A ResourceMapWrapper object to control which resourcemap
      Umpire http server should serve.
  """
  umpire_http_server = None
  umpire_base_handler = None
  umpire_handler = None

  umpire_http_server_process = None
  umpire_base_handler_process = None
  umpire_handler_process = None

  UMPIRE_BASE_HANDLER_PORT = None
  UMPIRE_HTTP_SERVER_PORT = None
  UMPIRE_HANDLER_PORT = None
  NUMBER_OF_PORTS = 5
  UMPIRE_SERVER_URI = None
  SHOPFLOOR_SERVER_URI = None

  mock_resourcemap = ResourceMapWrapper()

  @classmethod
  def setUpClass(cls):
    """Starts servers before running any test of this class."""
    # Copy testdata to some temporary directory.
    cls.temp_dir = tempfile.mkdtemp(
        prefix='umpire_server_proxy_testdata.')
    cls.temp_testdata_dir = os.path.join(cls.temp_dir, 'testdata')
    shutil.copytree(TESTDATA_DIRECTORY, cls.temp_testdata_dir)
    os.chdir(cls.temp_testdata_dir)
    port = net_utils.FindUnusedPort(tcp_only=True, length=cls.NUMBER_OF_PORTS)
    logging.debug('Set starting testing port to %r', port)
    cls.SetTestingPort(port)
    cls.SetupServers()

  @classmethod
  def SetTestingPort(cls, umpire_base_handler_port):
    """Sets testing port based on umpire_base_handler_port"""
    cls.UMPIRE_BASE_HANDLER_PORT = umpire_base_handler_port
    cls.UMPIRE_HTTP_SERVER_PORT = umpire_base_handler_port + 1
    cls.UMPIRE_HANDLER_PORT = umpire_base_handler_port + 2
    cls.UMPIRE_SERVER_URI = '%s:%d' % (MOCK_UMPIRE_ADDR,
                                       cls.UMPIRE_BASE_HANDLER_PORT)
    cls.SHOPFLOOR_SERVER_URI = '%s:%d' % (MOCK_UMPIRE_ADDR,
                                          cls.UMPIRE_HANDLER_PORT)

  @classmethod
  def tearDownClass(cls):
    """Stops servers in after running all test in this class."""
    cls.StopAllServers()
    if os.path.isdir(cls.temp_dir):
      shutil.rmtree(cls.temp_dir)

  @classmethod
  def SetupServers(cls):
    """Setups http server and xmlrpc handlers."""
    cls.SetupHTTPServer()
    cls.SetupHandlers()

  @classmethod
  def StopAllServers(cls):
    """Terminates processes for servers if they are still alive."""
    if cls.umpire_http_server_process.is_alive():
      process_utils.KillProcessTree(cls.umpire_http_server_process,
                                    'umpire_http_server')
    if cls.umpire_handler_process.is_alive():
      process_utils.KillProcessTree(cls.umpire_handler_process,
                                    'umpire_handler')
    if cls.umpire_base_handler_process.is_alive():
      process_utils.KillProcessTree(cls.umpire_base_handler_process,
                                    'base_handler')
    cls.umpire_http_server_process.join()
    cls.umpire_handler_process.join()
    cls.umpire_base_handler_process.join()
    logging.debug('All servers stopped')

  @classmethod
  def SetupHTTPServer(cls):
    """Setups http server in its own process."""
    logging.debug('Using UMPIRE_HTTP_SERVER_PORT: %r',
                  cls.UMPIRE_HTTP_SERVER_PORT)
    cls.umpire_http_server = SocketServer.TCPServer(
        ('', cls.UMPIRE_HTTP_SERVER_PORT), MockUmpireHTTPHandler)
    cls.umpire_http_server_process = multiprocessing.Process(
        target=RunServer, args=(cls.umpire_http_server,))
    cls.umpire_http_server_process.start()

  @classmethod
  def SetupHandlers(cls):
    """Setups xmlrpc servers and handlers in their own processes."""
    cls.umpire_base_handler = SimpleXMLRPCServer.SimpleXMLRPCServer(
        addr=('', cls.UMPIRE_BASE_HANDLER_PORT),
        requestHandler=MyXMLRPCRequestHandlerWrapper('base_handler'),
        allow_none=True,
        logRequests=True)
    cls.umpire_base_handler.register_function(PingOfUmpire, 'Ping')
    cls.umpire_base_handler_process = multiprocessing.Process(
        target=RunServer, args=(cls.umpire_base_handler,))
    cls.umpire_base_handler_process.start()

    cls.umpire_handler = SimpleXMLRPCServer.SimpleXMLRPCServer(
        ('', cls.UMPIRE_HANDLER_PORT),
        allow_none=True,
        logRequests=True)
    cls.umpire_handler.register_function(PingOfLegacyServer, 'Ping')
    cls.umpire_handler.register_function(LongBusyMethod, 'LongBusyMethod')
    cls.umpire_handler.register_function(
        HandlerFunctionWrapper('umpire_handler', use_umpire=True),
        UMPIRE_HANDLER_METHOD)
    cls.umpire_handler.register_function(
        HandlerFunctionWrapper('shopfloor_handler'),
        SHOPFLOOR_HANDLER_METHOD)
    cls.umpire_handler.register_introspection_functions()
    cls.umpire_handler_process = multiprocessing.Process(
        target=RunServer, args=(cls.umpire_handler,))
    cls.umpire_handler_process.start()

  def setUp(self):
    """Setups mox and mock umpire_client_info used in tests."""
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(umpire_client, 'UmpireClientInfo')
    self.fake_umpire_client_info = self.mox.CreateMockAnything()

  def ClearErrorFiles(self):
    """Clears obsolete error tag files generated for previous tests."""
    for p in glob.glob('error_*'):
      os.unlink(p)

  def tearDown(self):
    """Clean up for each test."""
    self.ClearErrorFiles()
    self.mox.UnsetStubs()

  def testGetResourceMapAndConnectToUmpireHandler(self):
    """Inits an UmpireServerProxy and connects to Umpire xmlrpc handler."""
    umpire_client.UmpireClientInfo().AndReturn(self.fake_umpire_client_info)
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

  def testHandleServerErrorMessageConnectionRefused(self):
    """Inits proxy but server is unavailable.

    Server version detection will be deferred to the time when method is
    invoked through proxy.
    """
    umpire_client.UmpireClientInfo().AndReturn(self.fake_umpire_client_info)
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
      proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi shopfloor')

    # Clear error files so base handler will not return 111 error.
    self.ClearErrorFiles()

    # retry after requesting resource map.
    result = proxy.__getattr__(SHOPFLOOR_HANDLER_METHOD)('hi umpire')
    self.assertEqual(
        result,
        'Handler: %s; message: %s' % ('shopfloor_handler', 'hi umpire'))

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
        'Handler: %s; message: %s' % ('shopfloor_handler', 'hi shopfloor'))

    self.mox.VerifyAll()
    logging.debug('Done')

  def testTimeoutUmpireServerProxy(self):
    """Proxy is working with ordinary shopfloor handler."""
    umpire_client.UmpireClientInfo().AndReturn(self.fake_umpire_client_info)
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
      unused_use_umpire = proxy.use_umpire

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
