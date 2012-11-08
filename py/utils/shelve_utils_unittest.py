#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os
import shelve
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import shelve_utils


def WipeFiles(parent_dir):
  """Clear all files in a directory."""
  for f in os.listdir(parent_dir):
    path = os.path.join(parent_dir, f)
    if os.path.isfile(path):
      open(path, 'w').close()


class ShelveUtilsTest(unittest.TestCase):
  def setUp(self):
    # Use a whole temp directory, since some DB mechanisms use multiple files.
    self.tmp = tempfile.mkdtemp(prefix='shelve_utils_unittest.')
    self.shelf_path = os.path.join(self.tmp, 'shelf')

  def tearDown(self):
    shutil.rmtree(self.tmp)

  def testIsShelfValid(self):
    shelf = shelve.open(self.shelf_path, 'c')
    shelf['FOO'] = 'BAR'
    del shelf

    self.assertTrue(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertTrue(shelve_utils.BackupShelfIfValid(self.shelf_path))

    # Corrupt the shelf by clearing all files in the temp directory.
    WipeFiles(self.tmp)

    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(self.shelf_path))

    # No worries, we have a backup!
    shelf = shelve_utils.OpenShelfOrBackup(self.shelf_path)
    self.assertEquals('BAR', shelf['FOO'])
    shelf['FOO'] = 'BAZ'
    del shelf

    # Open and close the shelf with OpenShelfOrBackup.  Now 'BAZ' should
    # be backed up.
    shelve_utils.OpenShelfOrBackup(self.shelf_path).close()
    self.assertTrue(shelve_utils.IsShelfValid(self.shelf_path))
    WipeFiles(self.tmp)
    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    shelf = shelve_utils.OpenShelfOrBackup(self.shelf_path)
    self.assertEquals('BAZ', shelf['FOO'])

  def testIsShelfValid_Nonexistent(self):
    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(self.shelf_path))

  def testIsShelfValid_EmptyFile(self):
    open(self.shelf_path, 'w').close()
    self.assertFalse(shelve_utils.IsShelfValid(self.shelf_path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(self.shelf_path))

  def testIsShelfValid_Corrupt(self):
    # This corrupt gdbm database causes the process to abort entirely.
    path = os.path.join(os.path.dirname(__file__),
                        'testdata', 'corrupt-gdbm-shelf')
    self.assertTrue(os.path.exists(path))
    self.assertFalse(shelve_utils.IsShelfValid(path))
    self.assertFalse(shelve_utils.BackupShelfIfValid(path))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
