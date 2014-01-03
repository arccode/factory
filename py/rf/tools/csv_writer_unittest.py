#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.rf.tools.csv_writer import WriteCsv
from cros.factory.utils.file_utils import UnopenedTemporaryFile


class CsvWriterTest(unittest.TestCase):
  def testReadSingleCell(self):
    with UnopenedTemporaryFile() as tmp_file:
      WriteCsv(tmp_file,
               [{'col_1': 1}, {'col_2': 2}, {'col_3': 3}],
               ['col_2', 'col_1'])
      with open(tmp_file, 'r') as fd:
        self.assertEqual(fd.readline().strip(), 'col_2,col_1,col_3')
        self.assertEqual(fd.readline().strip(), ',1,')
        self.assertEqual(fd.readline().strip(), '2,,')
        self.assertEqual(fd.readline().strip(), ',,3')

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
