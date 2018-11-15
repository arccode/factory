# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Loader of test_list.json"""

import collections
import logging
import os
import zipimport

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import checker as checker_module
from cros.factory.test.test_lists import test_list as test_list_module
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


# Directory for test lists.
TEST_LISTS_RELPATH = os.path.join('py', 'test', 'test_lists')
TEST_LISTS_PATH = os.path.join(paths.FACTORY_DIR, TEST_LISTS_RELPATH)

# File identifying the active test list.
ACTIVE_TEST_LIST_CONFIG_NAME = 'active_test_list'
ACTIVE_TEST_LIST_CONFIG_ID_KEY = 'id'

# The active test list ID is the most important factory data that we
# can't afford it to disappear unexpectedly.  Therefore, instead of
# saving it as a runtime configuration, we would rather saving it as
# a buildtime configuration manually.
ACTIVE_TEST_LIST_CONFIG_RELPATH = os.path.join(
    TEST_LISTS_RELPATH,
    ACTIVE_TEST_LIST_CONFIG_NAME + config_utils.CONFIG_FILE_EXT)
ACTIVE_TEST_LIST_CONFIG_PATH = os.path.join(
    paths.FACTORY_DIR, ACTIVE_TEST_LIST_CONFIG_RELPATH)

# Default test list.
DEFAULT_TEST_LIST_ID = 'main'

# All test lists must have name: <id>.test_list.json
CONFIG_SUFFIX = '.test_list'

TEST_LIST_SCHEMA_NAME = 'test_list'


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

  def __init__(self, config_dir=None):
    # TEST_LISTS_PATH depends on paths.FACTORY_DIR, which does not work in
    # factory par, however, currently, we should not run Goofy and test list
    # manager in factory par. The default_config_dirs config_utils.LoadConfig
    # will find should be the same one we compute here, however, we also need
    # this path to check file state, so let's figure out the path by ourselves.
    self.config_dir = config_dir or TEST_LISTS_PATH

  def Load(self, test_list_id, allow_inherit=True):
    """Loads test list config by test list ID.

    Returns:
      :rtype: TestListConfig
    """
    config_name = self._GetConfigName(test_list_id)
    try:
      loaded_config = config_utils.LoadConfig(
          config_name=config_name,
          schema_name=TEST_LIST_SCHEMA_NAME,
          validate_schema=True,
          default_config_dirs=self.config_dir,
          allow_inherit=allow_inherit,
          generate_depend=True)
    except Exception:
      logging.error('Cannot load test list "%s"', test_list_id)
      raise

    loaded_config = TestListConfig(
        resolved_config=loaded_config,
        test_list_id=test_list_id,
        source_path=loaded_config.GetDepend()[0])

    return loaded_config

  def _GetConfigName(self, test_list_id):
    """Returns the test list config file corresponding to `test_list_id`."""
    return test_list_id + CONFIG_SUFFIX

  def FindTestLists(self):
    """Returns a dict which maps the id to the file path of each test list."""
    globbed_configs = config_utils.GlobConfig(
        '*' + CONFIG_SUFFIX, default_config_dirs=self.config_dir)
    return [name[:-len(CONFIG_SUFFIX)] for name in globbed_configs]


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
      successfully.

    Raises:
      Exception if either the config is not found, is not loaded successfully,
      or check failed on test list.
    """
    if test_list_id in self.test_lists:
      self.test_lists[test_list_id].ReloadIfModified()
      return self.test_lists[test_list_id]

    config = self.loader.Load(test_list_id)

    if not isinstance(config, TestListConfig):
      raise ValueError('Loader is not returning a TestListConfig instance')

    try:
      test_list = test_list_module.TestList(config, self.checker, self.loader)
      self.test_lists[test_list_id] = test_list
      return test_list
    except Exception:
      logging.critical('Failed to build test list %r from config',
                       test_list_id)
      raise

  def GetTestListIDs(self):
    return self.test_lists.keys()

  def BuildAllTestLists(self):
    failed_test_lists = {}
    for test_list_id in self.loader.FindTestLists():
      logging.debug('try to load test list: %s', test_list_id)
      try:
        test_list = self.GetTestListByID(test_list_id)
      except Exception as e:
        logging.exception('Unable to load the test list %r', test_list_id)
        failed_test_lists[test_list_id] = str(e)

    valid_test_lists = {}  # test lists that will be returned
    for test_list_id, test_list in self.test_lists.iteritems():
      if isinstance(test_list, test_list_module.TestList):
        # if the test list does not have subtests, don't return it.
        # (this is a base test list)
        if 'tests' not in test_list.ToTestListConfig():
          continue
        try:
          test_list.CheckValid()
        except Exception as e:
          logging.exception('Test list %s is invalid', test_list_id)
          failed_test_lists[test_list_id] = repr(e)
          continue
      valid_test_lists[test_list_id] = test_list

    logging.debug('loaded test lists: %r', self.test_lists.keys())
    return valid_test_lists, failed_test_lists

  @staticmethod
  def GetActiveTestListId():
    """Returns the ID of the active test list.

    This method first try to load the active test list id by loading the
    ``active_test_list`` config file.  If there is no such configuration,
    'main' is returned.
    """
    try:
      config_data = config_utils.LoadConfig(
          config_name=ACTIVE_TEST_LIST_CONFIG_NAME,
          default_config_dirs=os.path.dirname(ACTIVE_TEST_LIST_CONFIG_PATH))
      return config_data[ACTIVE_TEST_LIST_CONFIG_ID_KEY]

    except config_utils.ConfigNotFoundError:
      logging.info('No active test list configuration is found, '
                   'fall back to select the default test list.')

    except Exception as e:
      logging.warning(
          'Failed to load the active test list configuration: %r.', e)

    return Manager.SelectDefaultTestList()

  @staticmethod
  def SelectDefaultTestList():
    model = process_utils.SpawnOutput(['mosys', 'platform', 'model']).strip()

    model_main = 'main_%s' % model

    for test_list_id in [model_main, 'main', 'generic_main']:
      if os.path.exists(os.path.join(
          TEST_LISTS_PATH,
          test_list_id + CONFIG_SUFFIX + config_utils.CONFIG_FILE_EXT)):
        return test_list_id
    return DEFAULT_TEST_LIST_ID

  @staticmethod
  def SetActiveTestList(new_id):
    """Sets the active test list.

    This writes the name of the new active test list to the build time config
    file.
    """
    config_data = json_utils.DumpStr({ACTIVE_TEST_LIST_CONFIG_ID_KEY: new_id})

    with file_utils.AtomicWrite(ACTIVE_TEST_LIST_CONFIG_PATH) as f:
      f.write(config_data)


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
