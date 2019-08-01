# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSONRPC-related utilities."""

from __future__ import print_function

from BaseHTTPServer import BaseHTTPRequestHandler
import inspect
import threading
import uuid

import jsonrpclib
from jsonrpclib import SimpleJSONRPCServer

from . import net_utils
from .net_utils import TimeoutXMLRPCTransport


class TimeoutJSONRPCTransport(jsonrpclib.jsonrpc.TransportMixIn,
                              TimeoutXMLRPCTransport):
  """JSON RPC enabled transport subclass support timeout.

  To use this transport with jsonrpclib.Server proxy, do:

    proxy = jsonrpclib.Server(server_url,
                              transport=TimeoutJSONRPCTransport(0.5))
  """

  def __init__(self, timeout):
    TimeoutXMLRPCTransport.__init__(self, timeout=timeout)
    jsonrpclib.jsonrpc.TransportMixIn.__init__(self)


class JSONRPCServer(object):
  """JSON RPC Server that runs in a separate thread."""

  def __init__(self, port, methods=None):
    self._server = None
    self._aborted = threading.Event()
    self._server_thread = None
    self._port = port
    self._methods = methods
    self._uuid = str(uuid.uuid4())

  def _ServeRPCForever(self):
    while not self._aborted.isSet():
      self._server.handle_request()

  def Start(self):
    self._server = SimpleJSONRPCServer.SimpleJSONRPCServer(
        ('0.0.0.0', self._port), logRequests=False)
    self._server.register_function(lambda: True, 'IsAlive')
    self._server.register_function(lambda: self._uuid, 'GetUuid')
    if self._methods:
      for k, v in self._methods.iteritems():
        self._server.register_function(v, k)
    self._server_thread = threading.Thread(target=self._ServeRPCForever,
                                           name='RPCServer')
    self._server_thread.daemon = True
    self._server_thread.start()

  def Destroy(self):
    if not self._server_thread:
      return
    self._aborted.set()
    # Make a fake request to self
    s = jsonrpclib.Server('http://%s:%d/' % (net_utils.LOCALHOST, self._port),
                          transport=TimeoutJSONRPCTransport(0.01))
    try:
      s.IsAlive()
    except Exception:
      pass
    self._server_thread.join()
    self._server.server_close()


def GetJSONRPCCallerIP():
  """Retrieve the IP address of the JSON RPC caller.

  This is a hack that depends on the implementation details of jsonrpclib.
  We know that JSON-RPC over HTTP requires a SimpleHTTPServer and
  SimpleJSONRPCRequestHandler dervies from SimpleXMLRPCRequestHandler, which
  derives from BaseHTTPRequestHandler. Thus we can extract the 'client_address'
  property of BaseHTTPRequestHandler, which is the address of the caller.
  """
  for st in inspect.stack():
    caller = st[0].f_locals.get('self', None)
    if caller and isinstance(caller, BaseHTTPRequestHandler):
      return caller.client_address[0]

  raise RuntimeError('no BaseHTTPRequestHandler found in stack')

class MultiPathJSONRPCRequestHandler(
    SimpleJSONRPCServer.SimpleJSONRPCRequestHandler):

  def is_rpc_path_valid(self):
    return self.server.is_rpc_path_valid(self.path)

class MultiPathJSONRPCServer(SimpleJSONRPCServer.SimpleJSONRPCServer):
  """Multipath JSON-RPC Server

  This specialization of SimpleJSONRPCServer allows the user to create
  multiple Dispatch instances and assign them to different
  HTTP request paths. This makes it possible to run two or more 'virtual
  JSON-RPC servers' at the same port.

  Make sure that the requestHandler accepts the paths by setting it's
  rpc_paths.

  Example usage:

  class MyHandler(SimpleJSONRPCRequestHandler):
    rpc_paths = ()

  class MyServer(SocketServer.ThreadingMixIn,
                 MultiPathJSONRPCServer):
    pass

  class MyRPCInstance(object):
    def Foo(self):
      pass

  server = MyServer(('localhost', 8080), requestHandler=MyHandler)

  dispatcher = SimpleJSONRPCServer.SimpleJSONRPCDispatcher()
  dispatcher.register_instance(MyRPCInstance())
  server.add_dispatcher('/MyRPC', dispatcher)

  server.serve_forever()

  # Now client can POST to http://localhost:8080/MyRPC
  """
  def __init__(self, addr,
               requestHandler=MultiPathJSONRPCRequestHandler,
               *args, **kwargs):
    SimpleJSONRPCServer.SimpleJSONRPCServer.__init__(
        self, addr, requestHandler, *args, **kwargs)
    self.dispatchers = {}

  def add_dispatcher(self, path, dispatcher):
    self.dispatchers[path] = dispatcher
    return dispatcher

  def get_dispatcher(self, path):
    return self.dispatchers[path]

  def is_rpc_path_valid(self, path):
    return path in self.dispatchers

  def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
    """Dispatch request

    This function is called by SimpleJSONRPCRequestHandler to dispatch request.
    """
    # TODO (shunhsingou): find other way instead of using inspect.
    handler = inspect.currentframe().f_back.f_locals['self']
    path = handler.path
    # pylint: disable=protected-access
    return self.dispatchers[path]._marshaled_dispatch(
        data, dispatch_method, path)
