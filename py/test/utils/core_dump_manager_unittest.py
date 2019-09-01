#!/usr/bin/env python2
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

import mox

import factory_common  # pylint: disable=unused-import
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
    self.mocker = mox.Mox()
    self.watched_file = None
    self.other_file = None

  def tearDown(self):
    shutil.rmtree(self.crash_dir)
    self.mocker.UnsetStubs()

  def testScan(self):
    logging.info('Test ScanFiles()')
    core_dump_manager.CoreDumpManager._SetCoreDump = (
        self.mocker.CreateMockAnything())
    core_dump_manager.CoreDumpManager._SetCoreDump()
    self.mocker.ReplayAll()
    manager = core_dump_manager.CoreDumpManager(
        watchlist=self.watchlist, crash_dir=self.crash_dir)
    self.CreateFiles()
    # Should get a list containing watched_file.
    self.assertEquals(manager.ScanFiles(), [self.watched_file.name])
    # Other files should get deleted in ScanFiles().
    self.assertEquals(os.listdir(self.crash_dir),
                      [os.path.basename(self.watched_file.name)])
    self.mocker.VerifyAll()

  def testScanNoWatch(self):
    logging.info('Test ScanFiles()')
    core_dump_manager.CoreDumpManager._SetCoreDump = (
        self.mocker.CreateMockAnything())
    core_dump_manager.CoreDumpManager._SetCoreDump()
    self.mocker.ReplayAll()
    manager = core_dump_manager.CoreDumpManager(
        crash_dir=self.crash_dir)
    self.CreateFiles()
    # Should get an empty list.
    self.assertEquals(manager.ScanFiles(), [])
    # All files should get deleted in ScanFiles().
    self.assertEquals(os.listdir(self.crash_dir), [])
    self.mocker.VerifyAll()

  def testClear(self):
    logging.info('Test ClearFiles()')
    core_dump_manager.CoreDumpManager._SetCoreDump = (
        self.mocker.CreateMockAnything())
    core_dump_manager.CoreDumpManager._SetCoreDump()
    self.mocker.ReplayAll()
    manager = core_dump_manager.CoreDumpManager(
        watchlist=self.watchlist, crash_dir=self.crash_dir)
    self.CreateFiles()
    watch_file = manager.ScanFiles()
    # Should get a list containing watched_file.
    # Other files should get deleted in ScanFiles().
    self.assertEquals(watch_file, [self.watched_file.name])
    manager.ClearFiles(watch_file)
    # The watched file is deleted after ClearFiles()
    self.assertEquals(os.listdir(self.crash_dir), [])
    self.mocker.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
