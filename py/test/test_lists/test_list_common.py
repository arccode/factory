# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.test.env import paths
from cros.factory.utils import config_utils


# Directory for test lists.
TEST_LISTS_RELPATH = os.path.join('py', 'test', 'test_lists')
TEST_LISTS_PATH = os.path.join(paths.FACTORY_DIR, TEST_LISTS_RELPATH)

# All test lists must have name: <id>.test_list.json.
TEST_LIST_CONFIG_SUFFIX = '.test_list'

# Test list schema.
TEST_LIST_SCHEMA_NAME = 'test_list'

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

# Test list constants config.
TEST_LIST_CONSTANTS_CONFIG_NAME = 'test_list_constants'


def GetTestListConfigName(test_list_id):
  """Returns the test list config name corresponding to `test_list_id`."""
  return test_list_id + TEST_LIST_CONFIG_SUFFIX


def GetTestListConfigFile(test_list_id):
  """Returns the test list config file corresponding to `test_list_id`."""
  return test_list_id + TEST_LIST_CONFIG_SUFFIX + config_utils.CONFIG_FILE_EXT


def GenerateActiveTestListConfig(active_test_list):
  """Returns a dictionary for active test list."""
  return {ACTIVE_TEST_LIST_CONFIG_ID_KEY: active_test_list}
