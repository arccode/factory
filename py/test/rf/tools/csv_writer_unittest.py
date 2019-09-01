#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rf.tools import csv_writer
from cros.factory.utils import file_utils


class CsvWriterTest(unittest.TestCase):

  def testReadSingleCell(self):
    with file_utils.UnopenedTemporaryFile() as tmp_file:
      csv_writer.WriteCsv(tmp_file,
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
