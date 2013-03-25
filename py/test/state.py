#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
This module provides both client and server side of a XML RPC based server which
can be used to handle factory test states (status) and shared persistent data.
'''

import factory_common # pylint: disable=W0611

import glob
import logging
import mimetypes
import os
import Queue
import re
import shelve
import shutil
import SocketServer
import sys
import threading
import time
import yaml

from hashlib import sha1
from uuid import uuid4

from jsonrpclib import jsonclass
from jsonrpclib import jsonrpc
from jsonrpclib import SimpleJSONRPCServer
from cros.factory import system
from cros.factory.test import factory
from cros.factory.test.factory import TestState
from cros.factory.test import unicode_to_string
from cros.factory.utils.shelve_utils import OpenShelfOrBackup
from cros.factory.utils.string_utils import CleanUTF8


DEFAULT_FACTORY_STATE_PORT = 0x0FAC
DEFAULT_FACTORY_STATE_ADDRESS = 'localhost'
DEFAULT_FACTORY_STATE_BIND_ADDRESS = 'localhost'
DEFAULT_FACTORY_STATE_FILE_PATH = factory.get_state_root()


def _synchronized(f):
  '''
  Decorates a function to grab a lock.
  '''
  def wrapped(self, *args, **kw):
    with self._lock: # pylint: disable=W0212
      return f(self, *args, **kw)
  return wrapped


def clear_state(state_file_path=None):
  '''Clears test state (removes the state file path).

  Args:
    state_file_path: Path to state; uses the default path if None.
  '''
  state_file_path = state_file_path or DEFAULT_FACTORY_STATE_FILE_PATH
  logging.warn('Clearing state file path %s' % state_file_path)
  if os.path.exists(state_file_path):
    shutil.rmtree(state_file_path)


class PathResolver(object):
  '''Resolves paths in URLs.'''
  def __init__(self):
    self._paths = {}

  def AddPath(self, url_path, local_path):
    '''Adds a prefix mapping:

    For example,

      AddPath('/foo', '/usr/local/docs')

    will cause paths to resolved as follows:

      /foo      -> /usr/local/docs
      /foo/index.html -> /usr/local/docs/index.html

    Args:
      url_path: The path in the URL
    '''
    self._paths[url_path] = local_path

  def Resolve(self, url_path):
    '''Resolves a path mapping.

    Returns None if no paths match.'

    Args:
      url_path: A path in a URL (starting with /).
    '''
    if not url_path.startswith('/'):
      return None

    prefix = url_path
    while prefix != '':
      local_prefix = self._paths.get(prefix)
      if local_prefix:
        return local_prefix + url_path[len(prefix):]
      prefix, _, _ = prefix.rpartition('/')

    root_prefix = self._paths.get('/')
    if root_prefix:
      return root_prefix + url_path


@unicode_to_string.UnicodeToStringClass
class FactoryState(object):
  '''
  The core implementation for factory state control.
  The major provided features are:

  SHARED DATA
    You can get/set simple data into the states and share between all tests.
    See get_shared_data(name) and set_shared_data(name, value) for more
    information.

  TEST STATUS
    To track the execution status of factory auto tests, you can use
    get_test_state, get_test_states methods, and update_test_state
    methods.

  All arguments may be provided either as strings, or as Unicode strings in
  which case they are converted to strings using UTF-8. All returned values
  are strings (not Unicode).

  This object is thread-safe.

  See help(FactoryState.[methodname]) for more information.

  Properties:
    _generated_files: Map from UUID to paths on disk. These are
      not persisted on disk (though they could be if necessary).
    _generated_data: Map from UUID to (mime_type, data) pairs for
      transient objects to serve.
    _generated_data_expiration: Priority queue of expiration times
      for objects in _generated_data.
  '''

  def __init__(self, state_file_path=None):
    '''
    Initializes the state server.

    Parameters:
      state_file_path:  External file to store the state information.
    '''
    state_file_path = state_file_path or DEFAULT_FACTORY_STATE_FILE_PATH
    if not os.path.exists(state_file_path):
      os.makedirs(state_file_path)
    self._tests_shelf = OpenShelfOrBackup(state_file_path + '/tests')
    self._data_shelf = OpenShelfOrBackup(state_file_path + '/data')
    self._lock = threading.RLock()
    self.test_list_struct = None

    self._generated_files = {}
    self._generated_data = {}
    self._generated_data_expiration = Queue.PriorityQueue()
    self._resolver = PathResolver()

    if TestState not in jsonclass.supported_types:
      jsonclass.supported_types.append(TestState)

  @_synchronized
  def close(self):
    '''
    Shuts down the state instance.
    '''
    for shelf in [self._tests_shelf,
                  self._data_shelf]:
      try:
        shelf.close()
      except:
        logging.exception('Unable to close shelf')

  @_synchronized
  def update_test_state(self, path, **kw):
    '''
    Updates the state of a test.

    See TestState.update for the allowable keyword arguments.

    @param path: The path to the test (see FactoryTest for a description
      of test paths).
    @param kw: See TestState.update for allowable arguments (e.g.,
      status and increment_count).

    @return: A tuple containing the new state, and a boolean indicating
      whether the state was just changed.
    '''
    state = self._tests_shelf.get(path)
    old_state_repr = repr(state)
    changed = False

    if not state:
      changed = True
      state = TestState()

    changed = changed | state.update(**kw) # Don't short-circuit

    if changed:
      logging.debug('Updating test state for %s: %s -> %s',
             path, old_state_repr, state)
      self._tests_shelf[path] = state
      self._tests_shelf.sync()

    return state, changed

  @_synchronized
  def get_test_state(self, path):
    '''
    Returns the state of a test.
    '''
    return self._tests_shelf[path]

  @_synchronized
  def get_test_paths(self):
    '''
    Returns a list of all tests' paths.
    '''
    return self._tests_shelf.keys()

  @_synchronized
  def get_test_states(self):
    '''
    Returns a map of each test's path to its state.
    '''
    return dict(self._tests_shelf)

  @_synchronized
  def clear_test_state(self):
    '''
    Clears all test state.
    '''
    self._tests_shelf.clear()

  def get_test_list(self):
    '''
    Returns the test list.
    '''
    return self.test_list.to_struct()

  @_synchronized
  def set_shared_data(self, *key_value_pairs):
    '''
    Sets shared data items.

    Args:
      key_value_pairs: A series of alternating keys and values
        (k1, v1, k2, v2...). In the simple case this can just
        be a single key and value.
    '''
    assert len(key_value_pairs) % 2 == 0, repr(key_value_pairs)
    for i in range(0, len(key_value_pairs), 2):
      self._data_shelf[key_value_pairs[i]] = key_value_pairs[i + 1]
    self._data_shelf.sync()

  @_synchronized
  def get_shared_data(self, key, optional=False):
    '''
    Retrieves a shared data item.

    Args:
      key: The key whose value to retrieve.
      optional: True to return None if not found; False to raise
        a KeyError.
    '''
    if optional:
      return self._data_shelf.get(key)
    else:
      return self._data_shelf[key]

  @_synchronized
  def has_shared_data(self, key):
    '''
    Returns if a shared data item exists.
    '''
    return key in self._data_shelf

  @_synchronized
  def del_shared_data(self, key, optional=False):
    '''
    Deletes a shared data item.

    Args:
      key: The key whose value to retrieve.
      optional: False to raise a KeyError if not found.
    '''
    try:
      del self._data_shelf[key]
    except KeyError:
      if not optional:
        raise

  @_synchronized
  def update_shared_data_dict(self, key, new_data):
    '''
    Updates values a shared data item whose value is a dictionary.

    This is roughly equivalent to

      data = get_shared_data(key) or {}
      data.update(new_data)
      set_shared_data(key, data)
      return data

    except that it is atomic.

    Args:
      key: The key for the data item to update.
      new_data: A dictionary of items to update.

    Returns:
      The updated value.
    '''
    data = self._data_shelf.get(key, {})
    data.update(new_data)
    self._data_shelf[key] = data
    return data

  def get_test_history(self, *test_paths):
    '''Returns metadata for all previous (and current) runs of a test.'''
    ret = []

    for path in test_paths:
      for f in glob.glob(os.path.join(factory.get_test_data_root(),
                                      path + '-*',
                                      'metadata')):
        try:
          ret.append(yaml.load(open(f)))
        except:
          logging.exception('Unable to load test metadata %s', f)

    ret.sort(key=lambda item: item.get('init_time', None))
    return ret

  def get_test_history_entry(self, path, invocation):
    '''Returns metadata and log for one test invocation.'''
    test_dir = os.path.join(factory.get_test_data_root(),
                            '%s-%s' % (path, invocation))

    log_file = os.path.join(test_dir, 'log')
    try:
      log = CleanUTF8(open(log_file).read())
    except:
      # Oh well
      logging.exception('Unable to read log file %s', log_file)
      log = None

    return {'metadata': yaml.load(open(os.path.join(test_dir, 'metadata'))),
            'log': log}

  @_synchronized
  def url_for_file(self, path):
    '''Returns a URL that can be used to serve a local file.

    Args:
     path: path to the local file

    Returns:
     url: A (possibly relative) URL that refers to the file
    '''
    uuid = str(uuid4())
    uri_path = '/generated-files/%s/%s' % (uuid, os.path.basename(path))
    self._generated_files[uuid] = path
    return uri_path

  @_synchronized
  def url_for_data(self, mime_type, data, expiration_secs=None):
    '''Returns a URL that can be used to serve a static collection
    of bytes.

    Args:
     mime_type: MIME type for the data
     data: Data to serve
     expiration_secs: If not None, the number of seconds in which
      the data will expire.
    '''
    uuid = str(uuid4())
    self._generated_data[uuid] = mime_type, data
    if expiration_secs:
      now = time.time()
      self._generated_data_expiration.put(
        (now + expiration_secs, uuid))

      # Reap old items.
      while True:
        try:
          item = self._generated_data_expiration.get_nowait()
        except Queue.Empty:
          break

        if item[0] < now:
          del self._generated_data[item[1]]
        else:
          # Not expired yet; put it back and we're done
          self._generated_data_expiration.put(item)
          break
    uri_path = '/generated-data/%s' % uuid
    return uri_path

  @_synchronized
  def register_path(self, url_path, local_path):
    self._resolver.AddPath(url_path, local_path)

  def get_system_status(self):
    '''Returns system status information.

    This may include system load, battery status, etc. See
    system.SystemStatus().
    '''
    return system.SystemStatus().__dict__


def get_instance(address=DEFAULT_FACTORY_STATE_ADDRESS,
         port=DEFAULT_FACTORY_STATE_PORT):
  '''
  Gets an instance (for client side) to access the state server.

  @param address: Address of the server to be connected.
  @param port: Port of the server to be connected.
  @return An object with all public functions from FactoryState.
    See help(FactoryState) for more information.
  '''
  return jsonrpc.ServerProxy('http://%s:%d' % (address, port),
                verbose=False)


class MyJSONRPCRequestHandler(SimpleJSONRPCServer.SimpleJSONRPCRequestHandler):
  def do_GET(self):
    logging.debug('HTTP request for path %s', self.path)

    handler = self.server.handlers.get(self.path)
    if handler:
      return handler(self)

    match = re.match('^/generated-data/([-0-9a-f]+)$', self.path)
    if match:
      generated_data = self.server._generated_data.get(match.group(1))
      if not generated_data:
        logging.warn('Unknown or expired generated data %s',
               match.group(1))
        self.send_response(404)
        return

      mime_type, data = generated_data

      self.send_response(200)
      self.send_header('Content-Type', mime_type)
      self.send_header('Content-Length', len(data))
      self.end_headers()
      self.wfile.write(data)

    if self.path.endswith('/'):
      self.path += 'index.html'

    if ".." in self.path.split("/"):
      logging.warn("Invalid path")
      self.send_response(404)
      return

    mime_type = mimetypes.guess_type(self.path)
    if not mime_type:
      logging.warn("Unable to guess MIME type")
      self.send_response(404)
      return

    local_path = None
    match = re.match('^/generated-files/([-0-9a-f]+)/', self.path)
    if match:
      local_path = self.server._generated_files.get(match.group(1))
      if not local_path:
        logging.warn('Unknown generated file %s in path %s',
               match.group(1), self.path)
        self.send_response(404)
        return

    local_path = self.server._resolver.Resolve(self.path)
    if not local_path or not os.path.exists(local_path):
      logging.warn("File not found: %s", (local_path or self.path))
      self.send_response(404)
      return

    self.send_response(200)
    self.send_header("Content-Type", mime_type[0])
    self.send_header("Content-Length", os.path.getsize(local_path))
    self.end_headers()
    with open(local_path) as f:
      shutil.copyfileobj(f, self.wfile)


class ThreadedJSONRPCServer(SocketServer.ThreadingMixIn,
              SimpleJSONRPCServer.SimpleJSONRPCServer):
  '''The JSON/RPC server.

  Properties:
    handlers: A map from URLs to callbacks handling them. (The callback
      takes a single argument: the request to handle.)
  '''
  def __init__(self, *args, **kwargs):
    SimpleJSONRPCServer.SimpleJSONRPCServer.__init__(self, *args, **kwargs)
    self.handlers = {}

  def add_handler(self, url, callback):
    self.handlers[url] = callback


def create_server(state_file_path=None, bind_address=None, port=None):
  '''
  Creates a FactoryState object and an JSON/RPC server to serve it.

  @param state_file_path: The path containing the saved state.
  @param bind_address: Address to bind to, defaulting to
    DEFAULT_FACTORY_STATE_BIND_ADDRESS.
  @param port: Port to bind to, defaulting to DEFAULT_FACTORY_STATE_PORT.
  @return A tuple of the FactoryState instance and the SimpleJSONRPCServer
    instance.
  '''
  # We have some icons in SVG format, but this isn't recognized in
  # the standard Python mimetypes set.
  mimetypes.add_type('image/svg+xml', '.svg')

  if not bind_address:
    bind_address = DEFAULT_FACTORY_STATE_BIND_ADDRESS
  if not port:
    port = DEFAULT_FACTORY_STATE_PORT
  instance = FactoryState(state_file_path)
  instance._resolver.AddPath(
    '/',
    os.path.join(factory.FACTORY_PACKAGE_PATH, 'goofy/static'))

  server = ThreadedJSONRPCServer(
    (bind_address, port),
    requestHandler=MyJSONRPCRequestHandler,
    logRequests=False)

  # Give the server the information it needs to resolve URLs.
  server._generated_files = instance._generated_files
  server._generated_data = instance._generated_data
  server._resolver = instance._resolver

  server.register_introspection_functions()
  server.register_instance(instance)
  server.web_socket_handler = None
  return instance, server
