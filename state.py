#!/usr/bin/env python
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
This module provides both client and server side of a XML RPC based server which
can be used to handle factory test states (status) and shared persistent data.
'''


import logging
import os
import shelve
import shutil
import SimpleXMLRPCServer
import sys
import threading
import xmlrpclib

import factory_common
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import TestState


FACTORY_STATE_VERSION = 2
DEFAULT_FACTORY_STATE_PORT = 0x0FAC
DEFAULT_FACTORY_STATE_ADDRESS = 'localhost'
DEFAULT_FACTORY_STATE_BIND_ADDRESS = 'localhost'
DEFAULT_FACTORY_STATE_FILE_PATH = os.path.join(
    factory.get_log_root(), 'factory_state.v%d' % FACTORY_STATE_VERSION)


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

    This object is thread-safe.

    See help(FactoryState.[methodname]) for more information.
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
        self._lock = threading.RLock()

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

    @_synchronized
    def set_shared_data(self, key, value):
        '''
        Sets a shared data item.
        '''
        self._data_shelf[key] = value
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


def get_instance(address=DEFAULT_FACTORY_STATE_ADDRESS,
                 port=DEFAULT_FACTORY_STATE_PORT):
    '''
    Gets an instance (for client side) to access the state server.

    @param address: Address of the server to be connected.
    @param port: Port of the server to be connected.
    @return An object with all public functions from FactoryState.
        See help(FactoryState) for more information.
    '''
    return xmlrpclib.ServerProxy('http://%s:%d' % (address, port),
                                 allow_none=True, verbose=False)


def create_server(state_file_path=None, bind_address=None, port=None):
    '''
    Creates a FactoryState object and an XML/RPC server to serve it.

    @param state_file_path: The path containing the saved state.
    @param bind_address: Address to bind to, defaulting to
        DEFAULT_FACTORY_STATE_BIND_ADDRESS.
    @param port: Port to bind to, defaulting to DEFAULT_FACTORY_STATE_PORT.
    @return A tuple of the FactoryState instance and the SimpleXMLRPCServer
        instance.
    '''
    if not bind_address:
        bind_address = DEFAULT_FACTORY_STATE_BIND_ADDRESS
    if not port:
        port = DEFAULT_FACTORY_STATE_PORT
    instance = FactoryState(state_file_path)
    server = SimpleXMLRPCServer.SimpleXMLRPCServer((bind_address, port),
                                                   allow_none=True,
                                                   logRequests=False)
    server.register_introspection_functions()
    server.register_instance(instance)
    return instance, server
