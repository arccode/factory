# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test list builder."""


from collections import namedtuple
import os
import threading

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths


# Directory for test lists.
TEST_LISTS_PATH = os.path.join(paths.FACTORY_DIR, 'py', 'test', 'test_lists')

# State used to build test lists.
#
# Properties:
#   stack: A stack of items being built.  stack[0] is always a TestList
#       (if one is currently being built).
#   test_lists: A dictionary (id, test_list_object) of all test lists
#       that have been built or are being built.
#   in_teardown: A boolean, we are in a subtree of teardown tests.
builder_state = threading.local()

# Sampling is the helper class to control sampling of tests in test list.
# key: The key used in device_data which will be evaluated in run_if argument.
# rate:
#   0.0: 0% sampling rate
#   1.0: 100% sampling rate
SamplingRate = namedtuple('SamplingRate', ['key', 'rate'])

# String prefix to indicate this value needs to be evaluated
EVALUATE_PREFIX = 'eval! '


class TestListError(Exception):
  """TestList exception"""
  pass
