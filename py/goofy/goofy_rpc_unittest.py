#!/usr/bin/env python
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from contextlib import contextmanager
import json
import os
import unittest

import mox
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy
from cros.factory.goofy import goofy_rpc
from cros.factory.test.env import paths
from cros.factory.test.test_lists import test_list as test_list_module
from cros.factory.utils import file_utils


@contextmanager
def ReplaceAttribute(obj, name, value):
  old_value = getattr(obj, name)
  setattr(obj, name, value)
  try:
    yield
  finally:
    setattr(obj, name, old_value)


class GoofyRPCTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.goofy = self.mox.CreateMock(goofy)
    self.goofy_rpc = goofy_rpc.GoofyRPC(self.goofy)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testGetTestList(self):
    test_list = "data"
    self.goofy.test_list = self.mox.CreateMock(test_list_module.FactoryTestList)
    self.goofy.test_list.ToStruct(extra_fields=['path']).AndReturn(test_list)

    self.mox.ReplayAll()

    self.assertEqual(
        test_list,
        self.goofy_rpc.GetTestList())

  def testGetTestHistory(self):
    data = {'A': 1, 'b': 'abc'}
    test_path = 'a.b.c'
    invocations = ['123', '456']
    expected = []

    for invocation in invocations:
      path = os.path.join(paths.DATA_TESTS_DIR,
                          test_path + '-%s' % invocation,
                          'metadata')
      file_utils.TryMakeDirs(os.path.dirname(path))
      with open(path, 'w') as f:
        data['init_time'] = invocation
        yaml.dump(data, f, default_flow_style=False)
      expected.append(data.copy())

    self.assertEqual(expected, self.goofy_rpc.GetTestHistory(test_path))

  def testGetTestHistoryEntry(self):
    path = 'a.b.c'
    invocation = '123'

    log = 'This is the test log'
    data = {'A': 1, 'b': 'abc'}

    test_dir = os.path.join(paths.DATA_TESTS_DIR,
                            '%s-%s' % (path, invocation))

    file_utils.TryMakeDirs(test_dir)
    log_file = os.path.join(test_dir, 'log')
    metadata_file = os.path.join(test_dir, 'metadata')
    testlog_file = os.path.join(test_dir, 'testlog.json')

    with open(log_file, 'w') as f:
      f.write(log)

    with open(metadata_file, 'w') as f:
      yaml.dump(data, f)

    with open(testlog_file, 'w') as f:
      json.dump(data, f)

    self.assertEqual(
        {'metadata': data,
         'testlog': data,
         'log': log},
        self.goofy_rpc.GetTestHistoryEntry(path, invocation))


if __name__ == '__main__':
  unittest.main()
