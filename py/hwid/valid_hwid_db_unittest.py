#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to verify that all v3 HWID databases are valid."""


import logging
import os
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.hwid import Database


class ValidHWIDDBsTest(unittest.TestCase):
  def runTest(self):
    hwid_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'chromeos-hwid')

    for board_name, board in yaml.load(
        open(os.path.join(hwid_dir, 'boards.yaml'))).iteritems():
      if board['version'] == 3:
        path = os.path.join(hwid_dir, board['path'])
        logging.info('Checking %s: %s', board_name, path)
        Database.LoadFile(path)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
