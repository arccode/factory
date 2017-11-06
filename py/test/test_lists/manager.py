# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Loader of test_list.json"""

import collections
import glob
import logging
import os
import re
import sys
import zipimport

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import checker as checker_module
from cros.factory.test.test_lists import test_list as test_list_module
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


# Directory for test lists.
TEST_LISTS_PATH = os.path.join(paths.FACTORY_DIR, 'py', 'test', 'test_lists')

# File identifying the active test list.
ACTIVE_PATH = os.path.join(TEST_LISTS_PATH, 'ACTIVE')

# Default test list.
DEFAULT_TEST_LIST_ID = 'main'


class TestListConfig(object):
  """A loaded test list config.

  This is a wrapper for ResolvedConfig, with some helper functions and caches.
  """
  def __init__(self, resolved_config, test_list_id, source_path=None):
    assert isinstance(resolved_config, config_utils.ResolvedConfig)
    self._resolved_config = resolved_config
    self._test_list_id = test_list_id
    self._depend = collections.OrderedDict()
    self.UpdateDependTimestamp()
    self._source_path = source_path

  def GetDepend(self):
    return self._depend

  def UpdateDependTimestamp(self):
    """Updates timestamps of dependency paths."""
    self._depend.clear()
    for path in self._resolved_config.GetDepend():
      self._depend[path] = self.GetTimestamp(path)

  @property
  def test_list_id(self):
    return self._test_list_id

  @property
  def source_path(self):
    return self._source_path

  def get(self, key, default=None):
    return self._resolved_config.get(key, default)

  def __getitem__(self, key):
    return self._resolved_config[key]

  def __iter__(self):
    return iter(self._resolved_config)

  def ToDict(self):
    return self._resolved_config.copy()

  @staticmethod
  def GetTimestamp(path):
    if os.path.exists(path):
      return os.stat(path).st_mtime
    if '.par' in path.lower():
      try:
        file_dir = os.path.dirname(path)
        importer = zipimport.zipimporter(file_dir)
        return os.stat(importer.archive).st_mtime
      except zipimport.ZipImportError:
        logging.warning('config_utils: No PAR/ZIP in %s. Ignore.', path)
      except IOError:
        logging.warning('config_utils: PAR path %s does not exist. Ignore.',
                        path)
    return None


class Loader(object):
  """Helper class to load a test list from given directory.

  The loader loads a JSON test list config from file system.  A loaded config
  will be `TestListConfig` object, which can be passed to `TestList` to create
  an `ITestList` object.
  """
  CONFIG_SUFFIX = '.test_list'
  """All test lists must have name: <id>.test_list.json"""

  ARGS_CONFIG_SUFFIX = '.test_list.args'
  """Config files with name: <id>.test_list.args.json can override arguments"""

  def __init__(self, schema_name='test_list', config_dir=None):
    self.schema_name = schema_name
    if not config_dir:
      # paths.FACTORY_DIR does not work in factory par, however, currently, we
      # should not run Goofy and test list manager in factory par.
      # The default_config_dirs config_utils.LoadConfig will find should be the
      # same one we compute here, however, we also need this path to check file
      # state, so let's figure out the path by ourselves.
      config_dir = os.path.join(paths.FACTORY_DIR,
                                'py', 'test', 'test_lists')
    self.config_dir = config_dir

  def Load(self, test_list_id, allow_inherit=True):
    """Loads test list config by test list ID.

    Returns:
      :rtype: TestListConfig
    """
    config_name = self._GetConfigName(test_list_id)
    try:
      loaded_config = config_utils.LoadConfig(
          config_name=config_name,
          schema_name=self.schema_name,
          validate_schema=True,
          default_config_dirs=self.config_dir,
          allow_inherit=allow_inherit,
          generate_depend=allow_inherit)
    except Exception:
      logging.exception('Cannot load test list "%s"', test_list_id)
      return None

    loaded_config = TestListConfig(
        resolved_config=loaded_config,
        test_list_id=test_list_id,
        source_path=self.GetConfigPath(test_list_id))

    return loaded_config

  def GetConfigPath(self, test_list_id):
    """Returns the test list config file path of `test_list_id`."""
    return os.path.join(self.config_dir,
                        self._GetConfigName(test_list_id) + '.json')

  def _GetConfigName(self, test_list_id):
    """Returns the test list config file corresponding to `test_list_id`."""
    return test_list_id + self.CONFIG_SUFFIX

  def _GetArgsConfigName(self, test_list_id):
    """Returns the test argument config file corresponding to `test_list_id`."""
    return test_list_id + self.ARGS_CONFIG_SUFFIX

  def FindTestListIDs(self):
    suffix = self.CONFIG_SUFFIX + '.json'
    return [os.path.basename(p)[:-len(suffix)] for p in
            glob.iglob(os.path.join(self.config_dir, '*' + suffix))]


class Manager(object):
  """Test List Manager.

  Attributes:
    test_configs: a dict maps a string (test list id) to loaded config file.
      Each loaded config file is just a json object, haven't been checked by
      `Checker` or merged with base test lists.
    test_lists: a dict maps a string (test list id) to loaded test list.
      Each loaded test list is a FactoryTestList object (or acts like one), have
      merged with base test lists and passed checker.
  """
  def __init__(self, loader=None, checker=None):
    self.loader = loader or Loader()
    self.checker = checker or checker_module.Checker()

    self.test_lists = {}

  def GetTestListByID(self, test_list_id):
    """Get test list by test list ID.

    Args:
      test_list_id: ID of the test list

    Returns:
      a TestList object if the corresponding test list config is loaded
      successfully, otherwise None.
    """
    if test_list_id in self.test_lists:
      self.test_lists[test_list_id].ReloadIfModified()
      return self.test_lists[test_list_id]

    config = self.loader.Load(test_list_id)
    if not config:
      # cannot load config file, return the value we currently have
      return self.test_lists.get(test_list_id, None)

    if not isinstance(config, TestListConfig):
      logging.critical('Loader is not returning a TestListConfig instance')
      return None

    try:
      test_list = test_list_module.TestList(config, self.checker, self.loader)
      self.test_lists[test_list_id] = test_list
    except Exception:
      logging.critical('Failed to build test list %r from config',
                       test_list_id)
    return self.test_lists.get(test_list_id, None)

  def GetTestListIDs(self):
    return self.test_lists.keys()

  def BuildAllTestLists(self):
    failed_files = {}
    for test_list_id in self.loader.FindTestListIDs():
      logging.debug('try to load test list: %s', test_list_id)
      try:
        test_list = self.GetTestListByID(test_list_id)
        if test_list is None:
          raise type_utils.TestListError('failed to load test list')
      except Exception:
        path = self.loader.GetConfigPath(test_list_id)
        logging.exception('Unable to import %s', path)
        failed_files[path] = sys.exc_info()

    valid_test_lists = {}  # test lists that will be returned
    for test_list_id, test_list in self.test_lists.iteritems():
      if isinstance(test_list, test_list_module.TestList):
        # if the test list does not have subtests, don't return it.
        # (this is a base test list)
        if 'tests' not in test_list.ToTestListConfig():
          continue
        try:
          test_list.CheckValid()
        except Exception:
          path = self.loader.GetConfigPath(test_list_id)
          logging.exception('test list %s is invalid', path)
          failed_files[path] = sys.exc_info()
          continue
      valid_test_lists[test_list_id] = test_list

    logging.debug('loaded test lists: %r', self.test_lists.keys())
    return valid_test_lists, failed_files

  @staticmethod
  def GetActiveTestListId():
    """Returns the ID of the active test list.

    This is read from the py/test/test_lists/ACTIVE file, if it exists.
    If there is no ACTIVE file, then 'main' is returned.
    """
    # Make sure it's a real file (and the user isn't trying to use the
    # old symlink method).
    if os.path.islink(ACTIVE_PATH):
      raise type_utils.TestListError(
          '%s is a symlink (should be a file containing a test list ID)' %
          ACTIVE_PATH)

    # Make sure "active" doesn't exist; it should be ACTIVE.
    wrong_caps_file = os.path.join(
        os.path.dirname(ACTIVE_PATH), os.path.basename(ACTIVE_PATH).lower())
    if os.path.lexists(wrong_caps_file):
      raise type_utils.TestListError(
          'Wrong spelling (%s) for active test list file (should be %s)' %
          (wrong_caps_file, ACTIVE_PATH))

    if not os.path.exists(ACTIVE_PATH):
      return DEFAULT_TEST_LIST_ID

    with open(ACTIVE_PATH) as f:
      test_list_id = f.read().strip()
      if re.search(r'\s', test_list_id):
        raise type_utils.TestListError(
            '%s should contain only a test list ID' % test_list_id)
      return test_list_id

  @staticmethod
  def SetActiveTestList(new_id):
    """Sets the active test list.

    This writes the name of the new active test list to ACTIVE_PATH.
    """
    with open(ACTIVE_PATH, 'w') as f:
      f.write(new_id + '\n')
      f.flush()
      os.fdatasync(f)


def BuildTestListForUnittest(test_list_config, manager=None):
  """Build a test list from loaded config.

  This function should only be used by unittests.
  """
  if not manager:
    manager = Manager()

  base_config = Loader().Load('base', False).ToDict()
  # Provide more default values for base_config.
  base_config = config_utils.OverrideConfig(
      {
          'label': 'label',
          'options': {
              'plugin_config_name': 'goofy_plugin_goofy_unittest'
          }
      },
      base_config)
  config = config_utils.OverrideConfig(base_config, test_list_config)
  config = config_utils.ResolvedConfig(config)
  config = TestListConfig(config, test_list_id='test')
  test_list = test_list_module.TestList(config, manager.checker, manager.loader)
  return test_list


def DummyTestList(manager):
  config = Loader().Load('base', False).ToDict()
  config = config_utils.OverrideConfig(
      {
          'label': 'Dummy',
          'tests': []
      },
      config)
  config = config_utils.ResolvedConfig(config)
  return test_list_module.TestList(
      TestListConfig(config, test_list_id='dummy'),
      manager.checker,
      manager.loader)
