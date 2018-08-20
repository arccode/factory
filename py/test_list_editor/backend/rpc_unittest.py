#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import manager
from cros.factory.test_list_editor.backend import rpc
from cros.factory.utils import file_utils


class RPCTest(unittest.TestCase):

  def testGetTestListSchema(self):
    rpc_obj = rpc.RPC([])
    json.loads(rpc_obj.GetTestListSchema())

  def testLoadFiles(self):
    rpc_obj = rpc.RPC([('', paths.FACTORY_DIR)])
    res = rpc_obj.LoadFiles()
    json.loads(res['files']['generic_main.test_list.json'])

  def testSaveFiles(self):
    with file_utils.TempDirectory() as tmp_dir:
      test_list_dir = os.path.join(tmp_dir, manager.TEST_LISTS_RELPATH)
      os.makedirs(test_list_dir)
      rpc_obj = rpc.RPC([('', tmp_dir)])
      content = 'hello, world'

      filepath = os.path.join(test_list_dir, 'a.test_list.json')
      rpc_obj.SaveFiles({filepath: content})
      self.assertEqual(file_utils.ReadFile(filepath), content)

      filepath = os.path.join(test_list_dir, 'a.test_list.orz')
      self.assertRaises(RuntimeError, rpc_obj.SaveFiles, {filepath: content})

      filepath = os.path.join(tmp_dir, 'orz', 'a.test_list.json')
      self.assertRaises(RuntimeError, rpc_obj.SaveFiles, {filepath: content})


if __name__ == '__main__':
  unittest.main()
