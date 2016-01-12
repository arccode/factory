# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""End-to-end tests for pytests."""

import glob
import os

import factory_common  # pylint: disable=W0611
from cros.factory.test.env import paths
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestList


def CreateTestLists():
  test_module_paths = [
      os.path.join(paths.FACTORY_PATH, 'py', 'test', 'pytests',
                   '*', '*_e2etest.py'),
      os.path.join(paths.FACTORY_PATH, 'py', 'test', 'pytests',
                   '*_e2etest.py'),
  ]
  with TestList('e2e-test', 'End-to-end tests for factory tests'):
    for path in test_module_paths:
      for test in glob.glob(path):
        e2e_test_name = os.path.splitext(os.path.basename(test))[0]
        OperatorTest(
            id=e2e_test_name,
            pytest_name=e2e_test_name)
