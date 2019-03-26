#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import converter
from cros.factory.hwid.v3.database import Database
from cros.factory.utils import json_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class ConvertToProbeStatementTest(unittest.TestCase):
  @mock.patch('cros.factory.probe.probe_utils.GenerateProbeStatement',
              return_value={'c1': {'generic': {'eval': 'aaa'}},
                            'c2': {'generic': {'eval': 'bbb'}}})
  def testNormal(self, unused_generate_probe_statement_mock):
    database = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_converter_db.yaml'),
        verify_checksum=False)
    result = json_utils.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_converter_result.json'),
        convert_to_str=False)
    self.assertEquals(converter.ConvertToProbeStatement(
        database, 'fake_probe_statement_path'), result)


if __name__ == '__main__':
  unittest.main()
