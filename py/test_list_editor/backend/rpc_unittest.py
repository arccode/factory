#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import numbers
import os
import unittest
from unittest import mock

from cros.factory.test.env import paths
from cros.factory.test.test_lists import test_list_common
from cros.factory.test_list_editor.backend import rpc
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


class _FakePytest:
  ARGS = [
      Arg('x', (bool, int, float, str), 'xxx', default=None),
      Arg(
          'y',
          (numbers.Integral,
           numbers.Number,
           list,
           dict,
           type_utils.Enum(('B', 'A'))),
          'yyy')
  ]


class RPCTest(unittest.TestCase):

  def testLoadFiles(self):
    rpc_obj = rpc.RPC([('', paths.FACTORY_DIR)])
    res = rpc_obj.LoadFiles()
    json.loads(res['files']['generic_main.test_list.json'])

  def testSaveFiles(self):
    with file_utils.TempDirectory() as tmp_dir:
      test_list_dir = os.path.join(tmp_dir, test_list_common.TEST_LISTS_RELPATH)
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

  @mock.patch('cros.factory.test.utils.pytest_utils.GetPytestList')
  def testListPytests(self, m_get_pytests_list):
    m_get_pytests_list.return_value = ['xyz.py', 'abc/def.py']
    rpc_obj = rpc.RPC([('', '')])
    self.assertEqual(rpc_obj.ListPytests(), ['abc.def', 'xyz'])

  @mock.patch('cros.factory.test.utils.pytest_utils.LoadPytest')
  @mock.patch('cros.factory.utils.file_utils.ReadFile')
  def testGetPytestInfo(self, m_read_file, m_load_pytest):
    src = 'hello, my happiness'
    m_read_file.return_value = src
    rpc_obj = rpc.RPC([])
    type_utils.LazyProperty.Override(rpc_obj, '_pytests', {'a': None})

    m_load_pytest.side_effect = ImportError
    self.assertEqual(rpc_obj.GetPytestInfo('a'), {'src': src})

    m_load_pytest.side_effect = None
    m_load_pytest.return_value = _FakePytest
    self.assertEqual(
        rpc_obj.GetPytestInfo('a'),
        {
            'src': src,
            'args': {
                'x': {
                    'type': ['BOOL', 'INT', 'STR', 'FLOAT', 'NONE'],
                    'help': 'xxx',
                    'default': None
                },
                'y': {
                    'type': ['INT', 'FLOAT', 'LIST', 'DICT', ['A', 'B']],
                    'help': 'yyy'
                }
            }
        })


if __name__ == '__main__':
  unittest.main()
