#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os.path
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import validator
from cros.factory.hwid.v3.database import Database


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class ValidatorTest(unittest.TestCase):
  def testGoodDramField(self):
    db = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_database_db_good_dram_tag.yaml'))
    # pylint: disable=protected-access
    validator._ValidateDramTag(db)

  def testBadDramField1(self):
    db = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_database_db_bad_dram_tag1.yaml'))
    with self.assertRaises(validator.ValidationError) as error:
      # pylint: disable=protected-access
      validator._ValidateDramTag(db)
    self.assertEqual(
        str(error.exception),
        'dram_type_256mb_and_real_is_512mb does not match size property 1024M')

  def testGoodDramField2(self):
    db = Database.LoadFile(
        os.path.join(_TEST_DATA_PATH, 'test_database_db_bad_dram_tag2.yaml'))
    with self.assertRaises(validator.ValidationError) as error:
      # pylint: disable=protected-access
      validator._ValidateDramTag(db)
    self.assertEqual(
        str(error.exception),
        'Invalid DRAM: dram_type_not_mention_size')


if __name__ == '__main__':
  unittest.main()
