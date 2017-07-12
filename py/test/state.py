#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This module handles factory test states (status) and shared persistent data.

The `state` provides two different data set using shelve_utils.DictShelfView:

 - tests: A shelf storing test states and status.
 - data: A shelf for data to be shared (also known as shared_data), providing:
   - device: Data and configuration of current DUT (usually accumulated from
     shopfloor or barcode scanner). See cros.factory.test.device_data for more
     details.
   - other global or session variables.
"""


from __future__ import print_function

import logging
import os
import shutil
import threading

from jsonrpclib import jsonclass

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import goofy_proxy
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import shelve_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


# TODO(shunhsingou): Remove the following legacy code.
# Support legacy code. Now the port and address information is defined in
# goofy_proxy module instead of here.
DEFAULT_FACTORY_STATE_PORT = goofy_proxy.DEFAULT_GOOFY_PORT
DEFAULT_FACTORY_STATE_ADDRESS = goofy_proxy.DEFAULT_GOOFY_ADDRESS

DEFAULT_FACTORY_STATE_FILE_DIR = paths.DATA_STATE_DIR

KEY_POST_SHUTDOWN = '%s.post_shutdown'

# dummy object to detect not set keyward argument
_DEFAULT_NOT_SET = object()

# Key for device data.  This is a dictionary of accumulated data usually from
# shopfloor calls with information about the configuration of the device.
KEY_DEVICE_DATA = 'device'


def clear_state(state_file_dir=DEFAULT_FACTORY_STATE_FILE_DIR):
  """Clears test state (removes the state file path).

  Args:
    state_file_dir: Path to state; uses the default path if None.
  """
  logging.warn('Clearing state file path %s', state_file_dir)
  if os.path.exists(state_file_dir):
    shutil.rmtree(state_file_dir)


class FactoryStateLayer(object):
  """Contains two DictShelfView 'tests_shelf' and 'data_shelf'."""
  def __init__(self, state_dir=None):
    """Constructor

    Args:
      state_dir: Where the shelves should be save to.  If this is None, shelves
        will be in memory shelf.
    """
    if state_dir:
      file_utils.TryMakeDirs(state_dir)
      self._tests_shelf = shelve_utils.DictShelfView(
          shelve_utils.OpenShelfOrBackup(os.path.join(state_dir, 'tests')))
      self._data_shelf = shelve_utils.DictShelfView(
          shelve_utils.OpenShelfOrBackup(os.path.join(state_dir, 'data')))
    else:
      self._tests_shelf = shelve_utils.DictShelfView(
          shelve_utils.InMemoryShelf())
      self._data_shelf = shelve_utils.DictShelfView(
          shelve_utils.InMemoryShelf())

  @property
  def tests_shelf(self):
    return self._tests_shelf

  @property
  def data_shelf(self):
    return self._data_shelf

  def Close(self):
    for shelf in [self._tests_shelf, self._data_shelf]:
      try:
        shelf.Close()
      except Exception:
        logging.exception('Unable to close shelf')


# TODO(shunhsingou): move goofy or dut related functions to goofy_rpc so we can
# really separate them.
@type_utils.UnicodeToStringClass
class FactoryState(object):
  """The core implementation for factory state control.

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
  """

  _TEST_STATE_POSTFIX = '__test_state__'

  def __init__(self, state_file_dir=None):
    """Initializes the state server.

    Parameters:
      state_file_dir:  External file to store the state information.
    """
    state_file_dir = state_file_dir or DEFAULT_FACTORY_STATE_FILE_DIR

    self.layers = [FactoryStateLayer(state_file_dir)]

    self._lock = threading.RLock()

    if factory.TestState not in jsonclass.supported_types:
      jsonclass.supported_types.append(factory.TestState)

  @sync_utils.Synchronized
  def close(self):
    """Shuts down the state instance."""
    for layer in self.layers:
      layer.Close()

  def _convert_test_path_to_key(self, path):
    return shelve_utils.DictKey.Join(path, self._TEST_STATE_POSTFIX)

  def _convert_key_to_test_path(self, key):
    test_path, postfix = shelve_utils.DictKey.Split(key)
    assert postfix == self._TEST_STATE_POSTFIX
    return test_path

  @sync_utils.Synchronized
  def update_test_state(self, path, **kw):
    """Updates the state of a test.

    See factory.TestState.update for the allowable keyword arguments.

    Args:
      path: The path to the test (see FactoryTest for a description
          of test paths).
      kw: See factory.TestState.update for allowable arguments (e.g.,
          status and increment_count).

    Returns:
      A tuple containing the new state, and a boolean indicating whether the
      state was just changed.
    """
    key = self._convert_test_path_to_key(path)
    for layer in self.layers:
      state = layer.tests_shelf.GetValue(key, optional=True)
      old_state_repr = repr(state)
      changed = False

      if not state:
        changed = True
        state = factory.TestState()

      changed = changed | state.update(**kw)  # Don't short-circuit

      if changed:
        logging.debug('Updating test state for %s: %s -> %s',
                      path, old_state_repr, state)
        layer.tests_shelf.SetValue(key, state)

    return state, changed

  @sync_utils.Synchronized
  def get_test_state(self, path):
    """Returns the state of a test."""
    key = self._convert_test_path_to_key(path)
    # when accessing, we need to go from top layer to bottom layer
    for layer in reversed(self.layers):
      try:
        return layer.tests_shelf.GetValue(key)
      except KeyError:
        pass
    raise KeyError(key)

  @sync_utils.Synchronized
  def get_test_paths(self):
    """Returns a list of all tests' paths."""
    # GetKeys() only returns keys that are mapped to a value, therefore, all
    # keys returned should end with `self._TEST_STATE_POSTFIX`.
    keys = set()
    for layer in self.layers:
      keys |= set(layer.tests_shelf.GetKeys())
    return [self._convert_key_to_test_path(key) for key in keys]

  @sync_utils.Synchronized
  def get_test_states(self):
    """Returns a map of each test's path to its state."""
    return {path: self.get_test_state(path) for path in self.get_test_paths()}

  @sync_utils.Synchronized
  def clear_test_state(self):
    """Clears all test state."""
    for layer in self.layers:
      layer.tests_shelf.Clear()

  @sync_utils.Synchronized
  def set_shared_data(self, key, value):
    """Sets shared data item."""
    self.data_shelf_set_value(key, value)

  @sync_utils.Synchronized
  def get_shared_data(self, key, optional=False):
    """Retrieves a shared data item.

    Args:
      key: The key whose value to retrieve.
      optional: True to return None if not found; False to raise a KeyError.
    """
    return self.data_shelf_get_value(key, optional)

  @sync_utils.Synchronized
  def has_shared_data(self, key):
    """Returns if a shared data item exists."""
    return self.data_shelf_has_key(key)

  @sync_utils.Synchronized
  def del_shared_data(self, key, optional=False):
    """Deletes a shared data item.

    Args:
      key: The key whose value to delete.
      optional: False to raise a KeyError if not found.
    """
    self.data_shelf_delete_keys([key], optional)

  @sync_utils.Synchronized
  def update_shared_data_dict(self, key, new_data):
    """Updates values a shared data item whose value is a dictionary.

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
    """
    self.data_shelf_update_value(key, new_data)
    return self.data_shelf_get_value(key, True) or {}

  @sync_utils.Synchronized
  def delete_shared_data_dict_item(self, shared_data_key,
                                   delete_keys, optional):
    """Deletes items from a shared data item whose value is a dict.

    This is roughly equivalent to

      data = get_shared_data(shared_data_key) or {}
      for key in delete_keys:
        try:
          del data[key]
        except KeyError:
          if not optional:
            raise
      set_shared_data(shared_data_key, data)
      return data

    except that it is atomic.

    Args:
      shared_data_key: The key for the data item to update.
      delete_keys: A list of keys to delete from the dict.
      optional: False to raise a KeyError if not found.

    Returns:
      The updated value.
    """
    self.data_shelf_delete_keys(
        [shelve_utils.DictKey.Join(shared_data_key, key)
         for key in delete_keys],
        optional)
    return self.data_shelf_get_value(shared_data_key, True) or {}

  @sync_utils.Synchronized
  def append_shared_data_list(self, key, new_item):
    """Appends an item to a shared data item whose value is a list.

    This is roughly equivalent to

      data = get_shared_data(key) or []
      data.append(new_item)
      set_shared_data(key, data)
      return data

    except that it is atomic.

    Args:
      key: The key for the data item to append.
      new_item: The item to be appended.

    Returns:
      The updated value.
    """
    data = self.data_shelf_get_value(key, optional=True) or []
    data.append(new_item)
    self.data_shelf_set_value(key, data)
    return data

  #############################################################################
  # The following functions are exposed for data_shelf APIs.
  # In the future, *_shared_data APIs might be deprecated, users shall use
  # `state_proxy.data_shelf.{GetValue, SetValue, GetKeys, ...}`, which use the
  # following functions.
  #
  # If there are multiple layers, only the last layer (self.layers[-1]) is
  # writable, 'set', 'update', 'delete' operations are only applied to the last
  # layer.
  #
  # For 'get' operation, all layers will be queried, and use
  # `config_utils.OverrideConfig` to merge each layers.  For a given key, if it
  # is mapped to different types in different layers, then the value will be
  # replaced without any warning or exception.  This might be confusing when it
  # is mapped to a dictionary in one of the layer, for example:
  #
  #   layers[1].data_shelf: { 'a': '456' }
  #   layers[0].data_shelf: { 'a': { 'b': '123' }}
  #
  #   data_shelf_get_value('a')  => '456'
  #   # since we will try to find 'a.b' in all layers, so 'a.b' is still valid.
  #   data_shelf_get_value('a.b') => '123'
  #
  # This should be okay since values in data_shelf should not change types.  If
  # it is a dict, it should always be a dict.
  #############################################################################
  @sync_utils.Synchronized
  def data_shelf_set_value(self, key, value):
    """Set key to value on top layer."""
    self.layers[-1].data_shelf.SetValue(key, value)

  @sync_utils.Synchronized
  def data_shelf_update_value(self, key, value):
    """Update key by value on top layer."""
    self.layers[-1].data_shelf.UpdateValue(key, value)

  @sync_utils.Synchronized
  def data_shelf_delete_keys(self, keys, optional=False):
    """Delete data with keys on top layer."""
    self.layers[-1].data_shelf.DeleteKeys(keys, optional=optional)

  @sync_utils.Synchronized
  def data_shelf_has_key(self, key):
    """Returns True if any layer contains the key."""
    return any(layer.data_shelf.HasKey(key) for layer in self.layers)

  @sync_utils.Synchronized
  def data_shelf_get_value(self, key, optional=False):
    """Get the merged value of given key.

    All layers will be read, and the values are merged by
    `config_utils.OverrideConfig`.  Therefore, if a key is mapped to different
    types in different layer, the behavior might seem strange.  For example::

        layers[0].data_shelf: { 'a': { 'b': '123' }}
        layers[1].data_shelf: { 'a': '456' }

        data_shelf_get_value('a')  => '456'
        data_shelf_get_value('a.b') => '123'

    Returns:
      A merged value, can be any JSON supported types.
    """
    DUMMY_KEY = 'result'
    value = {}

    for layer in self.layers:
      try:
        v = layer.data_shelf.GetValue(key, optional=False)
        value = config_utils.OverrideConfig(value, {DUMMY_KEY: v})
      except KeyError:
        pass
    if value:
      return value[DUMMY_KEY]
    if optional:
      return None
    raise KeyError(key)

  @sync_utils.Synchronized
  def data_shelf_get_children(self, key):
    """Returns children of given path (key)."""
    if not self.data_shelf_has_key(key):
      raise KeyError(key)

    ret = set()
    for layer in self.layers:
      try:
        ret |= set(layer.data_shelf.GetChildren(key))
      except KeyError:
        pass
    return list(ret)


class DataShelfSelector(object):
  """Data selector for data_shelf.

  data_shelf behaves like a recursive dictionary structure.  The
  DataShelfSelector helps you get data from this dictionary.

  For example, if the data stored in data_shelf is:

      {
        'a': {
          'b': {
            'c': 3
          }
        }
      }

  Then,

      selector.Get() shall return entire dictionary.

      selector['a'] shall return another selector rooted at 'a', thus
      selector['a'].Get() shall return {'b': {'c': 3}}.

      selector.GetValue('a') shall return {'b': {'c': 3}}
      selector['a'].GetValue('b') shall return {'c': 3}

      selector['a']['b'] and selector['a.b'] are equivalent, they both return a
      selector rooted at 'b'.
  """
  def __init__(self, proxy, key=''):
    """Constructor

    Args:
      :type proxy: FactoryState
      :type key: basestring
    """
    self._proxy = proxy
    self._key = key

  def SetValue(self, key, value):
    key = shelve_utils.DictKey.Join(self._key, key)

    self._proxy.data_shelf_set_value(key, value)

  def GetValue(self, key, default=_DEFAULT_NOT_SET):
    key = shelve_utils.DictKey.Join(self._key, key)

    if default == _DEFAULT_NOT_SET or self._proxy.data_shelf_has_key(key):
      return self._proxy.data_shelf_get_value(key, False)
    else:
      return default

  def Set(self, value):
    self.SetValue('', value)

  def Get(self, default=_DEFAULT_NOT_SET):
    return self.GetValue('', default=default)

  def __getitem__(self, key):
    key = shelve_utils.DictKey.Join(self._key, key)
    return self.__class__(self._proxy, key)

  def __setitem__(self, key, value):
    self.SetValue(key, value)

  def __iter__(self):
    return iter(self._proxy.data_shelf_get_children(self._key))

  def __contains__(self, key):
    return key in self._proxy.data_shelf_get_children(self._key)


def get_instance(address=None, port=None):
  """Gets an instance (for client side) to access the state server.

  Args:
    address: Address of the server to be connected.
    port: Port of the server to be connected.

  Returns:
    :rtype: cros.factory.test.state.FactoryState

    An object with all public functions from FactoryState.
    See help(FactoryState) for more information.
  """
  proxy = goofy_proxy.get_rpc_proxy(
      address, port, goofy_proxy.STATE_URL)
  proxy.__dict__['data_shelf'] = DataShelfSelector(proxy)
  return proxy


# ---------------------------------------------------------------------------
# Helper functions for shared data
def get_shared_data(key, default=None):
  if not get_instance().has_shared_data(key):
    return default
  return get_instance().get_shared_data(key)


def set_shared_data(key, value):
  return get_instance().set_shared_data(key, value)


def has_shared_data(key):
  return get_instance().has_shared_data(key)


def del_shared_data(key):
  return get_instance().del_shared_data(key)


class StubFactoryStateLayer(FactoryStateLayer):
  """Stub FactoryStateLayer for unittest."""
  def __init__(self, state_dir=None):
    del state_dir  # unused
    # always create in memory shelf
    self._tests_shelf = shelve_utils.DictShelfView(
        shelve_utils.InMemoryShelf())
    self._data_shelf = shelve_utils.DictShelfView(
        shelve_utils.InMemoryShelf())


class StubFactoryState(FactoryState):
  def __init__(self):  # pylint: disable=super-init-not-called
    self.layers = [StubFactoryStateLayer()]

    self._lock = threading.RLock()
    self.data_shelf = DataShelfSelector(self)
