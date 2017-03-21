#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Factory Update Server."""

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor import factory_update_server


# pylint: disable=W0212


BASE_DIR = os.path.dirname(os.path.realpath(__file__))
TESTDATA_MD5SUM = 'd9d51c02d1b40da5c7ddae311ff52597'


class BasicTests(unittest.TestCase):

  def testMd5sumCalculation(self):
    md5sum = factory_update_server.CalculateMd5sum(
        os.path.join(BASE_DIR, 'testdata/factory.tar.bz2'))
    self.assertEqual(md5sum, TESTDATA_MD5SUM)


class FactoryUpdateServerTest(unittest.TestCase):

  def setUp(self):
    self.work_dir = tempfile.mkdtemp(prefix='dts')
    self.update_server = None
    self._CreateUpdateServer()
    factory_update_server.poll_interval_sec = 0.1

  def _CreateUpdateServer(self):
    self.update_server = factory_update_server.FactoryUpdateServer(
        self.work_dir)

  def tearDown(self):
    self.update_server.Stop()
    self.assertEqual(0, self.update_server._errors)
    shutil.rmtree(self.work_dir)

  def testThread(self):
    # Start the thread (make sure it starts/stops properly).
    self.update_server.Start()
    self.update_server.Stop()
    self.assertTrue(self.update_server._run_count)

  def testNeedsUpdate(self):
    self.update_server.RunOnce()
    tarball_src = os.path.join(BASE_DIR, 'testdata/factory.tar.bz2')
    tarball_dest = os.path.join(self.work_dir, 'factory.tar.bz2')
    blacklist_path = os.path.join(self.work_dir, 'blacklist')
    # Put factory.tar.bz2 into the working folder.
    shutil.copy(tarball_src, tarball_dest)
    # Kick the update server
    self.update_server.RunOnce()

    # Test with no blacklist

    # Test with no md5sum
    self.assertTrue(self.update_server.NeedsUpdate(None))
    # Test with current md5sum
    self.assertFalse(self.update_server.NeedsUpdate(
        TESTDATA_MD5SUM))
    # Test with a different md5sum
    self.assertTrue(self.update_server.NeedsUpdate(
        'bb51d673f53129a2cc454e95e958e43e'))

    # Test with blacklist

    with open(blacklist_path, 'w') as f:
      f.write('bb51d673f53129a2cc454e95e958e43e')
    # Kick the update server to detect blacklist
    self.update_server.RunOnce()

    # Test with no md5sum
    self.assertTrue(self.update_server.NeedsUpdate(None))
    # Test with current md5sum
    self.assertFalse(self.update_server.NeedsUpdate(
        TESTDATA_MD5SUM))
    # Test with a different md5sum in blacklist
    self.assertFalse(self.update_server.NeedsUpdate(
        'bb51d673f53129a2cc454e95e958e43e'))

  def testLogic(self):
    self.update_server.RunOnce()

    self.assertTrue(os.path.isdir(os.path.join(self.work_dir, 'factory')))
    self.assertTrue(self.update_server._rsyncd.poll() is None)

    # No latest.md5sum file at the beginning.
    md5file = os.path.join(self.work_dir, 'factory/latest.md5sum')
    self.assertFalse(os.path.exists(md5file))
    self.assertEqual(0, self.update_server._update_count)

    tarball_src = os.path.join(BASE_DIR, 'testdata/factory.tar.bz2')
    tarball_dest = os.path.join(self.work_dir, 'factory.tar.bz2')

    # Put partially-written factory.tar.bz2 into the working folder.
    with open(tarball_dest, 'w') as f:
      f.write('Not really a bzip2')
    self.update_server.RunOnce()

    # Put factory.tar.bz2 into the working folder.
    shutil.copy(tarball_src, tarball_dest)
    # Kick the update server
    self.update_server.RunOnce()

    # Check that latest.md5sum is created with correct value and update files
    # extracted.
    self.assertTrue(os.path.isfile(md5file), md5file)
    with open(md5file, 'r') as f:
      self.assertEqual(TESTDATA_MD5SUM, f.read().strip())
    self.assertTrue(os.path.isdir(os.path.join(
        self.work_dir, 'factory/' + TESTDATA_MD5SUM)))
    self.assertEqual(1, self.update_server._update_count)

    # Kick the update server again.  Nothing should happen.
    self.update_server.RunOnce()
    self.assertEqual(1, self.update_server._update_count)

    # Stop the update server and set up a new one.  The md5sum file
    # should be recreated.
    self.update_server.Stop()
    del self.update_server
    os.unlink(md5file)
    self._CreateUpdateServer()
    self.update_server.RunOnce()
    with open(md5file, 'r') as f:
      self.assertEqual(TESTDATA_MD5SUM, f.read().strip())

if __name__ == '__main__':
  unittest.main()
