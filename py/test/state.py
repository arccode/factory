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

# Key for device data.  This is a dictionary of accumulated data usually from
# shopfloor calls with information about the configuration of the device.
KEY_DEVICE_DATA = 'device'


class FactoryStateLayerException(Exception):
  """Exception about FactoryStateLayer."""


def ClearState(state_file_dir=DEFAULT_FACTORY_STATE_FILE_DIR):
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

  def Loads(self, serialized_data):
    # There might be unicode string in serialized data (because serialized data
    # will not be processed by UnicodeToString).  But unicode string is not
    # allowed for shelve using gdbm, we need to convert them.
    o = type_utils.UnicodeToString(pickle.loads(serialized_data))
    if 'tests' in o:
      self.tests_shelf.SetValue('', o['tests'])
    if 'data' in o:
      self.data_shelf.SetValue('', o['data'])

  def Dumps(self, include_data, include_tests):
    o = {}
    # Only includes 'tests' or 'data' if they are set.
    # `GetValue(key, optional=True) == None` when key is not found.  But
    # `SetValue('', None)` will create a unwanted ('', None) key-value pair in
    # `self.Loads()`.
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
    See DataShelfGetValue(name) and DataShelfSetValue(name, value) for more
    information.

  TEST STATUS
    To track the execution status of factory auto tests, you can use
    GetTestState(), GetTestStates(), and UpdateTestState() methods.

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

    if TestState not in jsonclass.SUPPORTED_TYPES:
      jsonclass.SUPPORTED_TYPES = jsonclass.SUPPORTED_TYPES + (TestState, )

  @sync_utils.Synchronized
  def Close(self):
    """Shuts down the state instance."""
    for layer in self.layers:
      layer.Close()

  @classmethod
  def ConvertTestPathToKey(cls, path):
    return shelve_utils.DictKey.Join(path, cls.TEST_STATE_POSTFIX)

  @classmethod
  def ConvertKeyToTestPath(cls, key):
    test_path, postfix = shelve_utils.DictKey.Split(key)
    if postfix != cls.TEST_STATE_POSTFIX:
      raise KeyError('Invalid test path key: %r' % key)
    return test_path

  @sync_utils.Synchronized
  def UpdateTestState(self, path, **kw):
    """Updates the state of a test.

    See TestState.Update for the allowable keyword arguments.

    Args:
      path: The path to the test (see FactoryTest for a description
          of test paths).
      kw: See TestState.Update for allowable arguments (e.g.,
          status and increment_count).

    Returns:
      A tuple containing the new state, and a boolean indicating whether the
      state was just changed.
    """
    key = self.ConvertTestPathToKey(path)
    for layer in self.layers:
      state = layer.tests_shelf.GetValue(key, optional=True)
      old_state_repr = repr(state)
      changed = False

      if not state:
        changed = True
        state = TestState()

      changed = changed | state.Update(**kw)  # Don't short-circuit

      if changed:
        logging.debug('Updating test state for %s: %s -> %s',
                      path, old_state_repr, state)
        layer.tests_shelf.SetValue(key, state)

    return state, changed

  @sync_utils.Synchronized
  def GetTestState(self, path):
    """Returns the state of a test."""
    key = self.ConvertTestPathToKey(path)
    # when accessing, we need to go from top layer to bottom layer
    for layer in reversed(self.layers):
      try:
        return layer.tests_shelf.GetValue(key)
      except KeyError:
        pass
    raise KeyError(key)

  @sync_utils.Synchronized
  def GetTestPaths(self):
    """Returns a list of all tests' paths."""
    # GetKeys() only returns keys that are mapped to a value, therefore, all
    # keys returned should end with `self.TEST_STATE_POSTFIX`.
    keys = set()
    for layer in self.layers:
      keys |= set(layer.tests_shelf.GetKeys())
    return [self.ConvertKeyToTestPath(key) for key in keys]

  @sync_utils.Synchronized
  def GetTestStates(self):
    """Returns a map of each test's path to its state."""
    return {path: self.GetTestState(path) for path in self.GetTestPaths()}

  @sync_utils.Synchronized
  def ClearTestState(self):
    """Clears all test state."""
    for layer in self.layers:
      layer.tests_shelf.Clear()

  #############################################################################
  # The following functions are exposed for data_shelf APIs.
  # *SharedData APIs are deprecated. Users shall use
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
  #   DataShelfGetValue('a')  => '456'
  #   # since we will try to find 'a.b' in all layers, so 'a.b' is still valid.
  #   DataShelfGetValue('a.b') => '123'
  #
  # This should be okay since values in data_shelf should not change types.  If
  # it is a dict, it should always be a dict.
  #############################################################################
  @sync_utils.Synchronized
  def DataShelfGetValue(self, key, optional=False):
    """Get the merged value of given key.

    All layers will be read, and the values are merged by
    `config_utils.OverrideConfig`.  Therefore, if a key is mapped to different
    types in different layer, the behavior might seem strange.  For example::

        layers[0].data_shelf: { 'a': { 'b': '123' }}
        layers[1].data_shelf: { 'a': '456' }

        DataShelfGetValue('a')  => '456'
        DataShelfGetValue('a.b') => '123'

    Args:
      key: The key whose value to be retrieved.
      optional: If key is not found, True to return None and False to raise a
      KeyError

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
  def DataShelfSetValue(self, key, value):
    """Set key to value on top layer."""
    self.layers[-1].data_shelf.SetValue(key, value)

  @sync_utils.Synchronized
  def DataShelfUpdateValue(self, key, value):
    """Update key by value on top layer."""
    self.layers[-1].data_shelf.UpdateValue(key, value)

  @sync_utils.Synchronized
  def DataShelfDeleteKeys(self, keys, optional=False):
    """Delete data with keys on top layer."""
    # In case there's only one single key.
    if isinstance(keys, basestring):
      keys = [keys]
    self.layers[-1].data_shelf.DeleteKeys(keys, optional=optional)

  @sync_utils.Synchronized
  def DataShelfHasKey(self, key):
    """Returns True if any layer contains the key."""
    return any(layer.data_shelf.HasKey(key) for layer in self.layers)

  @sync_utils.Synchronized
  def DataShelfGetChildren(self, key):
    """Returns children of given path (key)."""
    if not self.DataShelfHasKey(key):
      raise KeyError(key)

    ret = set()
    for layer in self.layers:
      try:
        ret |= set(layer.data_shelf.GetChildren(key))
      except KeyError:
        pass
    return list(ret)

  @sync_utils.Synchronized
  def DataShelfAppendToList(self, key, new_item):
    """Appends data to a list with given key. d[key] += [new_item]."""
    data = self.DataShelfGetValue(key, optional=True) or []
    data.append(new_item)
    self.DataShelfSetValue(key, data)

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
      self.layers[-1].Loads(serialized_data)

  @sync_utils.Synchronized
  def PopLayer(self):
    if len(self.layers) == 1:
      raise FactoryStateLayerException('Cannot pop last layer')
    self.layers.pop()

  @sync_utils.Synchronized
  def SerializeLayer(self, layer_index, include_data=True, include_tests=True):
    layer = self.layers[layer_index]
    return layer.Dumps(include_data, include_tests)

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


def GetInstance(address=None, port=None):
  """Gets an instance (for client side) to access the state server.

  Args:
    address: Address of the server to be connected.
    port: Port of the server to be connected.

  Returns:
    :rtype: cros.factory.test.state.FactoryState

    An object with all public functions from FactoryState.
    See help(FactoryState) for more information.
  """
  proxy = goofy_proxy.GetRPCProxy(
      address, port, goofy_proxy.STATE_URL)
  proxy.data_shelf = DataShelfSelector(proxy)
  return proxy


# ---------------------------------------------------------------------------
# Helper functions for data shelf manipulation.

def DataShelfGetValue(key, default=None):
  if not GetInstance().DataShelfHasKey(key):
    return default
  return GetInstance().DataShelfGetValue(key)

def DataShelfSetValue(key, value):
  return GetInstance().DataShelfSetValue(key, value)

def DataShelfUpdateValue(key, value):
  return GetInstance().DataShelfUpdateValue(key, value)

def DataShelfHasKey(key):
  return GetInstance().DataShelfHasKey(key)

def DataShelfDeleteKeys(key, optional=False):
  return GetInstance().DataShelfDeleteKeys(key, optional)

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

  def Update(self, status=None, increment_count=0, error_msg=None,
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
  def FromDictOrObject(cls, obj):
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
