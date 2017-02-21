#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This module handles factory test states (status) and shared persistent data.
"""


from __future__ import print_function

import glob
from jsonrpclib import jsonclass
import logging
import os
import shutil
import threading
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.test.env import goofy_proxy
from cros.factory.test import factory
from cros.factory.utils import shelve_utils
from cros.factory.utils import string_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils

# TODO(shunhsingou): Remove the following legacy code.
# Support legacy code. Now the port and address information is defined in
# goofy_proxy module instead of here.
DEFAULT_FACTORY_STATE_PORT = goofy_proxy.DEFAULT_GOOFY_PORT
DEFAULT_FACTORY_STATE_ADDRESS = goofy_proxy.DEFAULT_GOOFY_ADDRESS

DEFAULT_FACTORY_STATE_FILE_PATH = paths.GetStateRoot()

POST_SHUTDOWN_TAG = '%s.post_shutdown'


def clear_state(state_file_path=DEFAULT_FACTORY_STATE_FILE_PATH):
  """Clears test state (removes the state file path).

  Args:
    state_file_path: Path to state; uses the default path if None.
  """
  logging.warn('Clearing state file path %s', state_file_path)
  if os.path.exists(state_file_path):
    shutil.rmtree(state_file_path)


# TODO(shunhsingou): move goofy or dut related functions to goofy_rpc so we can
# really separate them.
# TODO(shunhsingou): implement unittest for this class.
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

  def __init__(self, state_file_path=None):
    """Initializes the state server.

    Parameters:
      state_file_path:  External file to store the state information.
    """
    state_file_path = state_file_path or DEFAULT_FACTORY_STATE_FILE_PATH
    if not os.path.exists(state_file_path):
      os.makedirs(state_file_path)
    self._tests_shelf = shelve_utils.OpenShelfOrBackup(state_file_path + '/tests')
    self._data_shelf = shelve_utils.OpenShelfOrBackup(state_file_path + '/data')
    self._lock = threading.RLock()

    # TODO(hungte) Support remote dynamic DUT.
    self._dut = device_utils.CreateDUTInterface()

    if factory.TestState not in jsonclass.supported_types:
      jsonclass.supported_types.append(factory.TestState)

  @sync_utils.Synchronized
  def close(self):
    """Shuts down the state instance."""
    for shelf in [self._tests_shelf,
                  self._data_shelf]:
      try:
        shelf.close()
      except:  # pylint: disable=bare-except
        logging.exception('Unable to close shelf')

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
    state = self._tests_shelf.get(path)
    old_state_repr = repr(state)
    changed = False

    if not state:
      changed = True
      state = factory.TestState()

    changed = changed | state.update(**kw)  # Don't short-circuit

    if changed:
      logging.debug('Updating test state for %s: %s -> %s',
                    path, old_state_repr, state)
      self._tests_shelf[path] = state
      self._tests_shelf.sync()

    return state, changed

  @sync_utils.Synchronized
  def get_test_state(self, path):
    """Returns the state of a test."""
    return self._tests_shelf[path]

  @sync_utils.Synchronized
  def get_test_paths(self):
    """Returns a list of all tests' paths."""
    return self._tests_shelf.keys()

  @sync_utils.Synchronized
  def get_test_states(self):
    """Returns a map of each test's path to its state."""
    return dict(self._tests_shelf)

  @sync_utils.Synchronized
  def clear_test_state(self):
    """Clears all test state."""
    self._tests_shelf.clear()

  def get_test_list(self):
    """Returns the test list."""
    return self.test_list.to_struct()

  @sync_utils.Synchronized
  def set_shared_data(self, *key_value_pairs):
    """Sets shared data items.

    Args:
      key_value_pairs: A series of alternating keys and values
          (k1, v1, k2, v2...). In the simple case this can just
          be a single key and value.
    """
    assert len(key_value_pairs) % 2 == 0, repr(key_value_pairs)
    for i in range(0, len(key_value_pairs), 2):
      self._data_shelf[key_value_pairs[i]] = key_value_pairs[i + 1]
    self._data_shelf.sync()

  @sync_utils.Synchronized
  def get_shared_data(self, key, optional=False):
    """Retrieves a shared data item.

    Args:
      key: The key whose value to retrieve.
      optional: True to return None if not found; False to raise a KeyError.
    """
    if optional:
      return self._data_shelf.get(key)
    else:
      return self._data_shelf[key]

  @sync_utils.Synchronized
  def has_shared_data(self, key):
    """Returns if a shared data item exists."""
    return key in self._data_shelf

  @sync_utils.Synchronized
  def del_shared_data(self, key, optional=False):
    """Deletes a shared data item.

    Args:
      key: The key whose value to retrieve.
      optional: False to raise a KeyError if not found.
    """
    try:
      del self._data_shelf[key]
    except KeyError:
      if not optional:
        raise

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
    data = self._data_shelf.get(key, {})
    data.update(new_data)
    self._data_shelf[key] = data
    return data

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
    data = self._data_shelf.get(shared_data_key, {})
    for key in delete_keys:
      try:
        del data[key]
      except KeyError:
        if not optional:
          raise
    self._data_shelf[shared_data_key] = data
    return data

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
    data = self._data_shelf.get(key, [])
    data.append(new_item)
    self._data_shelf[key] = data
    return data

  def get_test_history(self, *test_paths):
    """Returns metadata for all previous (and current) runs of a test."""
    ret = []

    for path in test_paths:
      for f in glob.glob(os.path.join(paths.GetTestDataRoot(),
                                      path + '-*',
                                      'metadata')):
        try:
          ret.append(yaml.load(open(f)))
        except:  # pylint: disable=bare-except
          logging.exception('Unable to load test metadata %s', f)

    ret.sort(key=lambda item: item.get('init_time', None))
    return ret

  def get_test_history_entry(self, path, invocation):
    """Returns metadata and log for one test invocation."""
    test_dir = os.path.join(paths.GetTestDataRoot(),
                            '%s-%s' % (path, invocation))

    log_file = os.path.join(test_dir, 'log')
    try:
      log = string_utils.CleanUTF8(open(log_file).read())
    except:  # pylint: disable=bare-except
      # Oh well
      logging.exception('Unable to read log file %s', log_file)
      log = None

    return {'metadata': yaml.load(open(os.path.join(test_dir, 'metadata'))),
            'log': log}

  def get_system_status(self):
    """Returns system status information.

    This may include system load, battery status, etc. See
    cros.factory.device.status.SystemStatus. Return None
    if DUT is not local (station-based).
    """
    if self._dut.link.IsLocal():
      return self._dut.status.Snapshot().__dict__
    return None


def get_instance(address=None, port=None):
  """Gets an instance (for client side) to access the state server.

  Args:
    address: Address of the server to be connected.
    port: Port of the server to be connected.

  Returns:
    An object with all public functions from FactoryState.
    See help(FactoryState) for more information.
  """
  return goofy_proxy.get_rpc_proxy(
      address, port, goofy_proxy.STATE_URL)


class StubFactoryState(FactoryState):
  class InMemoryShelf(dict):
    def sync(self):
      pass

    def close(self):
      pass

  def __init__(self):  # pylint: disable=super-init-not-called
    self._tests_shelf = self.InMemoryShelf()
    self._data_shelf = self.InMemoryShelf()

    self._lock = threading.RLock()

  def get_system_status(self):
    # Mock this function if your unittest needs this.
    raise NotImplementedError
