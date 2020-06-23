# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Goofy server that handles Web request that Goofy needs."""

import logging
import mimetypes
import os
import queue
import shutil
import socketserver
import threading
import time
from uuid import uuid4

from jsonrpclib import SimpleJSONRPCServer

from cros.factory.utils import jsonrpc_utils
from cros.factory.utils import sync_utils


class PathResolver:
  """Resolves paths in URLs."""

  def __init__(self):
    self._paths = {}
    self._lock = threading.RLock()

  @sync_utils.Synchronized
  def AddPath(self, url_path, local_path):
    """Adds a prefix mapping:

    For example,

      AddPath('/foo', '/usr/local/docs')

    will cause paths to resolved as follows:

      /foo      -> /usr/local/docs
      /foo/index.html -> /usr/local/docs/index.html

    Args:
      url_path: The path in the URL
    """
    self._paths[url_path] = local_path

  @sync_utils.Synchronized
  def AddHandler(self, url_path, callback):
    """Adds a handler on url_path

    The handler should be a callback function that has the request object as
    the only argument.
    """
    self._paths[url_path] = callback

  @sync_utils.Synchronized
  def RemoveHandler(self, url_path):
    """Removes the handler"""
    del self._paths[url_path]

  def Resolve(self, url_path):
    """Resolves a path mapping.

    Returns the mapped file path or the handler. Returns None if no paths match.

    Args:
      url_path: A path in a URL (starting with /).
    """
    if not url_path.startswith('/'):
      return None

    prefix = url_path
    while prefix != '':
      value = self._paths.get(prefix)
      if value:
        suffix = url_path[len(prefix):]
        if isinstance(value, str):
          return value + suffix
        if suffix == '':
          return value
      prefix, unused_sep, suffix = prefix.rpartition('/')
      # For '/xxx', we also need to check '/' as the prefix.
      if prefix == '' and suffix != '':
        prefix = '/'
        url_path = '/' + url_path

    # Nothing found.
    return None


class GoofyWebRequestHandler(
    jsonrpc_utils.MultiPathJSONRPCRequestHandler):
  """RequestHandler used by GoofyServer

  This class extands SimpleJSONRPCRequestHandler to support HTTP GET request
  for Goofy server. See more explaination in GoofyServer.
  """

  def do_GET(self):
    logging.debug('HTTP GET request for path %s', self.path)

    if '..' in self.path.split('/'):
      logging.warning('Invalid path')
      self.send_response(404)
      self.end_headers()
      return

    if self.path.endswith('/'):
      self.path += 'index.html'

    # pylint: disable=protected-access
    callback_or_path = self.server._resolver.Resolve(self.path)

    if callable(callback_or_path):
      callback_or_path(self)
      return

    local_path = callback_or_path

    mime_type = mimetypes.guess_type(self.path)[0]
    if not mime_type:
      logging.warning('Unable to guess MIME type')
      mime_type = 'application/octet-stream'

    if not local_path or not os.path.exists(local_path):
      logging.warning('File not found: %s', (local_path or self.path))
      self.send_response(404)
      self.end_headers()
      return

    self.send_response(200)
    self.send_header('Content-Type', mime_type)
    self.send_header('Content-Length', os.path.getsize(local_path))
    self.end_headers()
    with open(local_path, 'rb') as f:
      shutil.copyfileobj(f, self.wfile)


class GoofyServer(socketserver.ThreadingMixIn,
                  jsonrpc_utils.MultiPathJSONRPCServer):
  """Server that handles Web request that Goofy used

  GoofyServer supports the following functions:

  - Multi-path JSON-RPC server: Handles different RPC instance on different
    URL. See document of
    `cros.factory.utils.jsonrpc_utils.MultiPathJSONRPCServer` and
    `AddRPCInstance` for detail.

  - Dynamically maps HTTP GET request to real path on the file system or data
    on the memory. See `RegisterPath`, `URLForFile`, `URLForData`.

  - JSON-RPC on '/' for `URLForFile` and `URLForData`. So those functions are
    also available on the client side.

  - Dynamically maps HTTP GET request to a callback function.
    See `AddHTTPGetHandler` for detail.
  """
  daemon_threads = True

  _PREFIX_GENERATED_FILE = '/generated-files'
  _PREFIX_GENERATED_DATA = '/generated-data'

  def __init__(self, addr, logRequests=False):
    # We have some icons in SVG format, but this isn't recognized in
    # the standard Python mimetypes set.
    mimetypes.add_type('image/svg+xml', '.svg')

    jsonrpc_utils.MultiPathJSONRPCServer.__init__(
        self, addr, requestHandler=GoofyWebRequestHandler,
        logRequests=logRequests)
    self._generated_data = {}
    self._generated_data_expiration = queue.PriorityQueue()
    self._resolver = PathResolver()

    # Used by sync_utils.Synchronized
    self._lock = threading.RLock()

    # Add RPC functions supported by this server.
    self.AddRPCInstance('/', GoofyServerRPC(self))

  @sync_utils.Synchronized
  def AddRPCInstance(self, url, instance):
    """Adds RPC instance to the server

    The public functions of `instance` would be available via in JSON-RPC call
    on `url`.

    Example usage:

    # Server
    class MyClass:
      def Foo(self):
        # Do something
        pass

    server.AddRPCInstance('/MyClass', MyClass())

    server.serve_forever()

    # Client
    from jsonrpclib import jsonrpc

    proxy = jsonrpc.ServerProxy('http://<address>:<port>/MyClass')
    proxy.Foo()
    """

    dispatcher = SimpleJSONRPCServer.SimpleJSONRPCDispatcher()
    dispatcher.register_introspection_functions()
    dispatcher.register_instance(instance)
    self.add_dispatcher(url, dispatcher)

  @sync_utils.Synchronized
  def AddHTTPGetHandler(self, url, callback):
    """Adds HTTP GET handler to the server

    The handle is a callback function that takes the request object as the only
    argument.
    """
    self._resolver.AddHandler(url, callback)

  @sync_utils.Synchronized
  def URLForFile(self, path):
    """Returns a URL that can be used to serve a local file.

    Args:
      path: path to the local file

    Returns:
      url: A (possibly relative) URL that refers to the file
    """
    uuid = str(uuid4())
    uri_path = '%s/%s/%s' % (self._PREFIX_GENERATED_FILE,
                             uuid,
                             os.path.basename(path))
    self._resolver.AddPath('%s/%s' % (self._PREFIX_GENERATED_FILE, uuid),
                           os.path.dirname(path))
    return uri_path

  @sync_utils.Synchronized
  def URLForData(self, mime_type, data, expiration_secs=None):
    """Returns a URL that can be used to serve a static collection of bytes.

    Args:
      mime_type: MIME type for the data
      data: Data to serve
      expiration_secs: If not None, the number of seconds in which
          the data will expire.
    """
    uuid = str(uuid4())
    uri_path = '%s/%s' % (self._PREFIX_GENERATED_DATA, uuid)
    self.RegisterData(uri_path, mime_type, data, expiration_secs)
    return uri_path

  def _HandleGetGeneratedData(self, handler, mime_type, data,
                              expiration_deadline=None):
    """The handler used by URLForData"""
    self._CheckGeneratedDataExpired()
    if expiration_deadline and time.time() > expiration_deadline:
      logging.warning('Expired generated data')
      handler.send_response(404)
      handler.end_headers()
      return

    if isinstance(data, str):
      data = data.encode('utf-8')

    handler.send_response(200)
    handler.send_header('Content-Type', mime_type)
    handler.send_header('Content-Length', len(data))
    handler.end_headers()
    handler.wfile.write(data)

  def _CheckGeneratedDataExpired(self):
    """Checks and expire temp data."""
    # Reap old items.
    now = time.time()
    while True:
      try:
        item = self._generated_data_expiration.get_nowait()
      except queue.Empty:
        break

      if item[0] < now:
        self._resolver.RemoveHandler(item[1])
      else:
        # Not expired yet; put it back and we're done
        self._generated_data_expiration.put(item)
        break

  @sync_utils.Synchronized
  def RegisterPath(self, url_path, local_path):
    """Register url_path to the local_path on the real file system"""
    self._resolver.AddPath(url_path, local_path)

  @sync_utils.Synchronized
  def RegisterData(self, url_path, mime_type, data, expiration_secs=None):
    """Register url_path to the data.

    URLForData should be used unless control for url_path is necessary.

    Args:
      url_path: The path to register
      mime_type: MIME type for the data
      data: Data to serve
      expiration_secs: If not None, the number of seconds in which
          the data will expire.
    """
    expiration_deadline = None

    if expiration_secs is not None:
      now = time.time()
      expiration_deadline = now + expiration_secs
      self._generated_data_expiration.put((expiration_deadline, url_path))

    self._resolver.AddHandler(
        url_path,
        lambda handler: self._HandleGetGeneratedData(
            handler, mime_type, data, expiration_deadline))

    self._CheckGeneratedDataExpired()

class GoofyServerRPC:
  """Native functions supported by GoofyServer."""
  def __init__(self, server):
    self._server = server

  def URLForData(self, mime_type, data, expiration_secs=None):
    return self._server.URLForData(mime_type, data, expiration_secs)

  def URLForFile(self, path):
    return self._server.URLForFile(path)

  def RegisterPath(self, url_path, local_path):
    return self._server.RegisterPath(url_path, local_path)
