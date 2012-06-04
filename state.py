#!/usr/bin/env python
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
This module provides both client and server side of a XML RPC based server which
can be used to handle factory test states (status) and shared persistent data.
'''


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

from hashlib import sha1
from uuid import uuid4

import factory_common

from jsonrpclib import jsonclass
from jsonrpclib import jsonrpc
from jsonrpclib import SimpleJSONRPCServer
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory import unicode_to_string

DEFAULT_FACTORY_STATE_PORT = 0x0FAC
DEFAULT_FACTORY_STATE_ADDRESS = 'localhost'
DEFAULT_FACTORY_STATE_BIND_ADDRESS = 'localhost'
DEFAULT_FACTORY_STATE_FILE_PATH = factory.get_state_root()


def _synchronized(f):
    '''
    Decorates a function to grab a lock.
    '''
    def wrapped(self, *args, **kw):
        with self._lock:  # pylint: disable=W0212
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


class TestHistoryItem(object):
    def __init__(self, path, state, log, trace=None):
        self.path = path
        self.state = state
        self.log = log
        self.trace = trace
        self.time = time.time()


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
    which case they are converted to strings using UTF-8.  All returned values
    are strings (not Unicode).

    This object is thread-safe.

    See help(FactoryState.[methodname]) for more information.

    Properties:
        _generated_files: Map from UUID to paths on disk.  These are
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
            state_file_path:    External file to store the state information.
        '''
        state_file_path = state_file_path or DEFAULT_FACTORY_STATE_FILE_PATH
        if not os.path.exists(state_file_path):
            os.makedirs(state_file_path)
        self._tests_shelf = shelve.open(state_file_path + '/tests')
        self._data_shelf = shelve.open(state_file_path + '/data')
        self._test_history_shelf = shelve.open(state_file_path +
                                               '/test_history')
        self._lock = threading.RLock()
        self.test_list_struct = None

        self._generated_files = {}
        self._generated_data = {}
        self._generated_data_expiration = Queue.PriorityQueue()

        if TestState not in jsonclass.supported_types:
            jsonclass.supported_types.append(TestState)

    @_synchronized
    def close(self):
        '''
        Shuts down the state instance.
        '''
        for shelf in [self._tests_shelf,
                      self._data_shelf,
                      self._test_history_shelf]:
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

        changed = changed | state.update(**kw)  # Don't short-circuit

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
                (k1, v1, k2, v2...).  In the simple case this can just
                be a single key and value.
        '''
        assert len(key_value_pairs) % 2 == 0, repr(key_value_pairs)
        for i in range(0, len(key_value_pairs), 2):
            self._data_shelf[key_value_pairs[i]] = key_value_pairs[i + 1]
        self._data_shelf.sync()

    @_synchronized
    def get_shared_data(self, key):
        '''
        Retrieves a shared data item.
        '''
        return self._data_shelf[key]

    @_synchronized
    def has_shared_data(self, key):
        '''
        Returns if a shared data item exists.
        '''
        return key in self._data_shelf

    @_synchronized
    def del_shared_data(self, key):
        '''
        Deletes a shared data item.
        '''
        del self._data_shelf[key]

    @_synchronized
    def add_test_history(self, history_item):
        path = history_item.path
        assert path

        length_key = path + '[length]'
        num_entries = self._test_history_shelf.get(length_key, 0)
        self._test_history_shelf[path + '[%d]' % num_entries] = history_item
        self._test_history_shelf[length_key] = num_entries + 1

    @_synchronized
    def get_test_history(self, paths):
        if type(paths) != list:
            paths = [paths]
        ret = []

        for path in paths:
            i = 0
            while True:
                value = self._test_history_shelf.get(path + '[%d]' % i)

                i += 1
                if not value:
                    break
                ret.append(value)

        ret.sort(key=lambda item: item.time)

        return ret

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
        logging.info('HTTP request for path %s', self.path)

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

        if self.path == "/":
            self.path = "/index.html"

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

        if not local_path:
            local_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                "static",
                self.path.lstrip("/"))

        if not os.path.exists(local_path):
            logging.warn("File not found: %s" % local_path)
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
        handlers: A map from URLs to callbacks handling them.  (The callback
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
    server = ThreadedJSONRPCServer(
        (bind_address, port),
        requestHandler=MyJSONRPCRequestHandler,
        logRequests=False)

    # Give the server the generated-files and -data maps.
    server._generated_files = instance._generated_files
    server._generated_data = instance._generated_data

    server.register_introspection_functions()
    server.register_instance(instance)
    server.web_socket_handler = None
    return instance, server
