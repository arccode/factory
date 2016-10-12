#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Verifies that new commits do not alter existing encoding patterns.

This test may be invoked in multiple ways:
  1. Execute manually. In this case all the v3 boards listed in boards.yaml
     are checked. The test loads and compares new and old databases from HEAD
     and HEAD~1, respectively, in each corresponding branch of each board.
  2. As a pre-submit check in platform/chromeos-hwid repo. In this case only the
     changed HWID databases in each commit are tested.
  3. VerifyParsedDatabasePattern may be called directly by the HWID Server.
"""

from __future__ import print_function

import argparse
import logging
import os
import subprocess
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.utils import process_utils
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.tools import build_board


class HWIDDBsPatternTest(unittest.TestCase):
  """Unit test for HWID database."""

  def __init__(self, board=None, commit=None):
    super(HWIDDBsPatternTest, self).__init__()
    self.board = board
    self.commit = commit

  def runTest(self):
    hwid_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'], 'src', 'platform', 'chromeos-hwid')
    if not os.path.exists(hwid_dir):
      print('ValidHWIDDBsTest: ignored, no %s in source tree.' % hwid_dir)
      return

    # Always read boards.yaml from ToT as all boards are required to have an
    # entry in it.
    boards_info = yaml.load(process_utils.CheckOutput(
        ['git', 'show', 'remotes/cros-internal/master:boards.yaml'],
        cwd=hwid_dir))
    files = os.environ.get('PRESUBMIT_FILES')
    if files:
      files = [f.partition('/platform/chromeos-hwid/')[-1]
               for f in files.splitlines()]
    else:
      # If PRESUBMIT_FILES is not found, defaults to test all v3 boards in
      # boards.yaml.
      files = [b['path'] for b in boards_info.itervalues() if b['version'] == 3]

    def TestDatabase(db_path):
      board_name = os.path.basename(db_path)
      if board_name not in boards_info:
        return
      commit = (self.commit or os.environ.get('PRESUBMIT_COMMIT') or
                'cros-internal/%s' % boards_info[board_name]['branch'])
      logging.info('Checking %s:%s...', commit, db_path)
      self.VerifyDatabasePattern(hwid_dir, commit, db_path)

    if self.board:
      if self.board not in boards_info:
        self.fail('Invalid board %r' % self.board)
      TestDatabase('v3/%s' % self.board)
    else:
      for f in files:
        TestDatabase(f)

  def VerifyDatabasePattern(self, hwid_dir, commit, db_path):
    try:
      old_db = database.Database.LoadData(
          yaml.load(process_utils.CheckOutput(
              ['git', 'show', '%s~1:%s' % (commit, db_path)],
              cwd=hwid_dir, ignore_stderr=True)),
          strict=False)
    except subprocess.CalledProcessError as e:
      if e.returncode == 128:
        logging.info('Adding new HWID database %s; skip pattern check',
                     os.path.basename(db_path))
        return
      raise

    new_db = database.Database.LoadData(
        yaml.load(process_utils.CheckOutput(
            ['git', 'show', '%s:%s' % (commit, db_path)],
            cwd=hwid_dir, ignore_stderr=True)),
        strict=False)

    try:
      HWIDDBsPatternTest.VerifyParsedDatabasePattern(old_db, new_db)
    except common.HWIDException as e:
      self.fail(e.message)

  @staticmethod
  def VerifyParsedDatabasePattern(old_db, new_db):
    # Make sure all the encoded fields in the existing patterns are not changed.
    for i in xrange(len(old_db.pattern.pattern)):
      dummy_image_id = old_db.pattern.pattern[i]['image_ids'][0]
      old_bit_mapping = old_db.pattern.GetBitMapping(image_id=dummy_image_id)
      new_bit_mapping = new_db.pattern.GetBitMapping(image_id=dummy_image_id)
      for index in old_bit_mapping.iterkeys():
        if new_bit_mapping[index] != old_bit_mapping[index]:
          raise common.HWIDException(
              'Bit pattern mismatch found at bit %d (encoded field=%r). '
              'If you are trying to append new bit(s), be sure to create a new '
              'bit pattern field instead of simply incrementing the last field' %
              (index, old_bit_mapping[index][0]))


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--board', help='the board to test')
  parser.add_argument('--commit', help='the commit to test')
  args = parser.parse_args()
  logging.basicConfig(level=logging.INFO)

  if args.board:
    args.board = build_board.BuildBoard(args.board).short_name.upper()
  runner = unittest.TextTestRunner()
  test = HWIDDBsPatternTest(board=args.board, commit=args.commit)
  runner.run(test)
