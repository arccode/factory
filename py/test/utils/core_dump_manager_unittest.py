#!/usr/bin/env python3
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=protected-access

import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock

from cros.factory.test.utils import core_dump_manager


class CoreDumpManagerTest(unittest.TestCase):

  def CreateFiles(self):
    self.watched_file = tempfile.NamedTemporaryFile(
        prefix='watch', dir=self.crash_dir, delete=False)
    self.other_file = tempfile.NamedTemporaryFile(
        prefix='other', dir=self.crash_dir, delete=False)

  def setUp(self):
    self.watchlist = ['*watch*']
    self.crash_dir = tempfile.mkdtemp(prefix='core_dump_manager_unittest.')
    self.watched_file = None
    self.other_file = None

  def tearDown(self):
    shutil.rmtree(self.crash_dir)

  @mock.patch(core_dump_manager.__name__ + '.CoreDumpManager._SetCoreDump')
  def testScan(self, set_core_dump_mock):
    logging.info('Test ScanFiles()')

    manager = core_dump_manager.CoreDumpManager(
        watchlist=self.watchlist, crash_dir=self.crash_dir)
    set_core_dump_mock.assert_called_once_with()

    self.CreateFiles()
    # Should get a list containing watched_file.
    self.assertEqual(manager.ScanFiles(), [self.watched_file.name])
    # Other files should get deleted in ScanFiles().
    self.assertEqual(os.listdir(self.crash_dir),
                     [os.path.basename(self.watched_file.name)])

  @mock.patch(core_dump_manager.__name__ + '.CoreDumpManager._SetCoreDump')
  def testScanNoWatch(self, set_core_dump_mock):
    logging.info('Test ScanFiles()')

    manager = core_dump_manager.CoreDumpManager(
        crash_dir=self.crash_dir)
    set_core_dump_mock.assert_called_once_with()

    self.CreateFiles()
    # Should get an empty list.
    self.assertEqual(manager.ScanFiles(), [])
    # All files should get deleted in ScanFiles().
    self.assertEqual(os.listdir(self.crash_dir), [])

  @mock.patch(core_dump_manager.__name__ + '.CoreDumpManager._SetCoreDump')
  def testClear(self, set_core_dump_mock):
    logging.info('Test ClearFiles()')

    manager = core_dump_manager.CoreDumpManager(
        watchlist=self.watchlist, crash_dir=self.crash_dir)
    set_core_dump_mock.assert_called_once_with()

    self.CreateFiles()
    watch_file = manager.ScanFiles()
    # Should get a list containing watched_file.
    # Other files should get deleted in ScanFiles().
    self.assertEqual(watch_file, [self.watched_file.name])
    manager.ClearFiles(watch_file)
    # The watched file is deleted after ClearFiles()
    self.assertEqual(os.listdir(self.crash_dir), [])


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
