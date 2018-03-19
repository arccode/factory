# Copyright 2012 The Chromium OS Authors. All rights reserved.
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

import cPickle as pickle
import logging
import os
import shutil
import threading

from jsonrpclib import jsonclass

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import goofy_proxy
from cros.factory.test.env import paths
from cros.factory.test.utils.selector_utils import DataShelfSelector
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import shelve_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


DEFAULT_FACTORY_STATE_FILE_DIR = paths.DATA_STATE_DIR

KEY_POST_SHUTDOWN = '%s.post_shutdown'

# dummy object to detect not set keyward argument
_DEFAULT_NOT_SET = object()

# Key for device data.  This is a dictionary of accumulated data usually from
# shopfloor calls with information about the configuration of the device.
KEY_DEVICE_DATA = 'device'


class FactoryStateLayerException(Exception):
  """Exception about FactoryStateLayer."""


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

  def loads(self, serialized_data):
    # There might be unicode string in serialized data (because serialized data
    # will not be processed by UnicodeToString).  But unicode string is not
    # allowed for shelve using gdbm, we need to convert them.
    o = type_utils.UnicodeToString(pickle.loads(serialized_data))
    if 'tests' in o:
      self.tests_shelf.SetValue('', o['tests'])
    if 'data' in o:
      self.data_shelf.SetValue('', o['data'])

  def dumps(self, include_data, include_tests):
    o = {}
    # Only includes 'tests' or 'data' if they are set.
    # `GetValue(key, optional=True) == None` when key is not found.  But
    # `SetValue('', None)` will create a unwanted ('', None) key-value pair in
    # `self.loads()`.
    if include_tests and self.tests_shelf.HasKey(''):
      o['tests'] = self.tests_shelf.GetValue('')
    if include_data and self.data_shelf.HasKey(''):
      o['data'] = self.data_shelf.GetValue('')
    return pickle.dumps(o)


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

  TEST_STATE_POSTFIX = '__test_state__'

  def __init__(self, state_file_dir=None):
    """Initializes the state server.

    Parameters:
      state_file_dir:  External file to store the state information.
    """
    state_file_dir = state_file_dir or DEFAULT_FACTORY_STATE_FILE_DIR

    self.layers = [FactoryStateLayer(state_file_dir)]

    self._lock = threading.RLock()

    if TestState not in jsonclass.supported_types:
      jsonclass.supported_types.append(TestState)

  @sync_utils.Synchronized
  def close(self):
    """Shuts down the state instance."""
    for layer in self.layers:
      layer.Close()

  @classmethod
  def convert_test_path_to_key(cls, path):
    return shelve_utils.DictKey.Join(path, cls.TEST_STATE_POSTFIX)

  @classmethod
  def convert_key_to_test_path(cls, key):
    test_path, postfix = shelve_utils.DictKey.Split(key)
    if postfix != cls.TEST_STATE_POSTFIX:
      raise KeyError('Invalid test path key: %r' % key)
    return test_path

  @sync_utils.Synchronized
  def update_test_state(self, path, **kw):
    """Updates the state of a test.

    See TestState.update for the allowable keyword arguments.

    Args:
      path: The path to the test (see FactoryTest for a description
          of test paths).
      kw: See TestState.update for allowable arguments (e.g.,
          status and increment_count).

    Returns:
      A tuple containing the new state, and a boolean indicating whether the
      state was just changed.
    """
    key = self.convert_test_path_to_key(path)
    for layer in self.layers:
      state = layer.tests_shelf.GetValue(key, optional=True)
      old_state_repr = repr(state)
      changed = False

      if not state:
        changed = True
        state = TestState()

      changed = changed | state.update(**kw)  # Don't short-circuit

      if changed:
        logging.debug('Updating test state for %s: %s -> %s',
                      path, old_state_repr, state)
        layer.tests_shelf.SetValue(key, state)

    return state, changed

  @sync_utils.Synchronized
  def get_test_state(self, path):
    """Returns the state of a test."""
    key = self.convert_test_path_to_key(path)
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
    # keys returned should end with `self.TEST_STATE_POSTFIX`.
    keys = set()
    for layer in self.layers:
      keys |= set(layer.tests_shelf.GetKeys())
    return [self.convert_key_to_test_path(key) for key in keys]

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

  #############################################################################
  # The following functions are exposed for layer APIs
  #############################################################################
  # Max number of layers allowed, including base layer.
  MAX_LAYER_NUM = 2

  @sync_utils.Synchronized
  def AppendLayer(self, serialized_data=None):
    if len(self.layers) == self.MAX_LAYER_NUM:
      raise FactoryStateLayerException('Max # layers reached')

    self.layers.append(FactoryStateLayer(None))
    if serialized_data:
      self.layers[-1].loads(serialized_data)

  @sync_utils.Synchronized
  def PopLayer(self):
    if len(self.layers) == 1:
      raise FactoryStateLayerException('Cannot pop last layer')
    self.layers.pop()

  @sync_utils.Synchronized
  def SerializeLayer(self, layer_index, include_data=True, include_tests=True):
    layer = self.layers[layer_index]
    return layer.dumps(include_data, include_tests)

  @sync_utils.Synchronized
  def MergeLayer(self, layer_index):
    if layer_index <= 0:
      raise IndexError('layer_index <= 0')
    if layer_index >= len(self.layers):
      raise IndexError('layer_index out of range')

    dst = self.layers[layer_index - 1]
    src = self.layers[layer_index]
    if src.tests_shelf.HasKey(''):
      dst.tests_shelf.UpdateValue('', src.tests_shelf.GetValue(''))
    if src.data_shelf.HasKey(''):
      dst.data_shelf.UpdateValue('', src.data_shelf.GetValue(''))
    self.layers.pop()

  @sync_utils.Synchronized
  def GetLayerCount(self):
    return len(self.layers)


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


class TestState(object):
  """The complete state of a test.

  Properties:
    status: The status of the test (one of ACTIVE, PASSED, FAILED, or UNTESTED).
    count: The number of times the test has been run.
    error_msg: The last error message that caused a test failure.
    shutdown_count: The number of times the test has caused a shutdown.
    invocation: The currently executing invocation.
    iterations_left: For an active test, the number of remaining iterations
        after the current one.
    retries_left: Maximum number of retries allowed to pass the test.
  """
  ACTIVE = 'ACTIVE'
  PASSED = 'PASSED'
  FAILED = 'FAILED'
  UNTESTED = 'UNTESTED'
  FAILED_AND_WAIVED = 'FAILED_AND_WAIVED'
  SKIPPED = 'SKIPPED'

  def __init__(self, status=UNTESTED, count=0, error_msg=None,
               shutdown_count=0, invocation=None, iterations_left=0,
               retries_left=0):
    self.status = status
    self.count = count
    self.error_msg = error_msg
    self.shutdown_count = shutdown_count
    self.invocation = invocation
    self.iterations_left = iterations_left
    self.retries_left = retries_left

  def __repr__(self):
    return type_utils.StdRepr(self)

  def update(self, status=None, increment_count=0, error_msg=None,
             shutdown_count=None, increment_shutdown_count=0,
             invocation=None,
             decrement_iterations_left=0, iterations_left=None,
             decrement_retries_left=0, retries_left=None):
    """Updates the state of a test.

    Args:
      status: The new status of the test.
      increment_count: An amount by which to increment count.
      error_msg: If non-None, the new error message for the test.
      shutdown_count: If non-None, the new shutdown count.
      increment_shutdown_count: An amount by which to increment shutdown_count.
      invocation: The currently executing or last invocation, if any.
      iterations_left: If non-None, the new iterations_left.
      decrement_iterations_left: An amount by which to decrement
          iterations_left.
      retries_left: If non-None, the new retries_left.
          The case retries_left = -1 means the test had already used the first
          try and all the retries.
      decrement_retries_left: An amount by which to decrement retries_left.

    Returns:
      True if anything was changed.
    """
    old_dict = dict(self.__dict__)

    if status:
      self.status = status
    if error_msg is not None:
      self.error_msg = error_msg
    if shutdown_count is not None:
      self.shutdown_count = shutdown_count
    if iterations_left is not None:
      self.iterations_left = iterations_left
    if retries_left is not None:
      self.retries_left = retries_left

    if invocation is not None:
      self.invocation = invocation

    self.count += increment_count
    self.shutdown_count += increment_shutdown_count
    self.iterations_left = max(
        0, self.iterations_left - decrement_iterations_left)
    # If retries_left is 0 after update, it is the usual case, so test
    # can be run for the last time. If retries_left is -1 after update,
    # it had already used the first try and all the retries.
    self.retries_left = max(
        -1, self.retries_left - decrement_retries_left)

    return self.__dict__ != old_dict

  @classmethod
  def from_dict_or_object(cls, obj):
    if isinstance(obj, dict):
      return TestState(**obj)
    else:
      assert isinstance(obj, TestState), type(obj)
      return obj

  def __eq__(self, other):
    return all(getattr(self, attr) == getattr(other, attr)
               for attr in self.__dict__)

  def ToStruct(self):
    result = dict(self.__dict__)
    for key in ['retries_left', 'iterations_left']:
      if result[key] == float('inf'):
        result[key] = -1
    return result


  @staticmethod
  def OverallStatus(statuses):
    """Returns the "overall status" given a list of statuses.

    This is the first element of

      [ACTIVE, FAILED, UNTESTED, FAILED_AND_WAIVED, PASSED]

    (in that order) that is present in the status list.
    """
    status_set = set(statuses)
    for status in [TestState.ACTIVE, TestState.FAILED,
                   TestState.UNTESTED, TestState.FAILED_AND_WAIVED,
                   TestState.SKIPPED, TestState.PASSED]:
      if status in status_set:
        return status

    # E.g., if statuses is empty
    return TestState.UNTESTED


# Stub classes for unittests

class StubFactoryStateLayer(FactoryStateLayer):
  """Stub FactoryStateLayer for unittest."""
  def __init__(self, state_dir=None):  # pylint: disable=super-init-not-called
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
