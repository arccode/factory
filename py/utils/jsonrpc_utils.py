# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSONRPC-related utilities."""

from __future__ import print_function

import jsonrpclib
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer
import threading
import uuid

import factory_common  # pylint: disable=W0611
from cros.factory.utils import net_utils
from cros.factory.utils.net_utils import TimeoutXMLRPCTransport


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
    self._server = SimpleJSONRPCServer(('0.0.0.0', self._port),
                                       logRequests=False)
    self._server.register_function(lambda: True, 'IsAlive')
    self._server.register_function(lambda: self._uuid, 'GetUuid')
    if self._methods:
      for k, v in self._methods.iteritems():
        self._server.register_function(v, k)
    self._server_thread = threading.Thread(target=self._ServeRPCForever,
                                           name='RPCServer')
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
    except: # pylint: disable=W0702
      pass
    self._server_thread.join()
    self._server.server_close()
