#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

from cros.factory.tools import install_symlinks


FAKE_SYMLINKS = {'binaries': {'fullbin': 'full', 'minibin': 'mini'}}


class TestInstallSymlinks(unittest.TestCase):

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp(prefix='install_symlinks_unittest.')

  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def testInstallFull(self):
    self.assertEqual(
        ['fullbin', 'minibin'],
        install_symlinks.InstallSymlinks(
            '../foo', self.tmpdir, install_symlinks.MODE_FULL,
            symlinks=FAKE_SYMLINKS))
    self.assertCountEqual(['fullbin', 'minibin'], os.listdir(self.tmpdir))
    self.assertEqual('../foo/fullbin',
                     os.readlink(os.path.join(self.tmpdir, 'fullbin')))
    self.assertEqual('../foo/minibin',
                     os.readlink(os.path.join(self.tmpdir, 'minibin')))

  def testInstallFullPar(self):
    self.assertEqual(
        ['fullbin', 'minibin'],
        install_symlinks.InstallSymlinks(
            '../foo.par', self.tmpdir, install_symlinks.MODE_FULL,
            symlinks=FAKE_SYMLINKS))
    self.assertCountEqual(['fullbin', 'minibin'], os.listdir(self.tmpdir))
    self.assertEqual('../foo.par',
                     os.readlink(os.path.join(self.tmpdir, 'fullbin')))
    self.assertEqual('../foo.par',
                     os.readlink(os.path.join(self.tmpdir, 'minibin')))

  def testInstallMini(self):
    self.assertEqual(['minibin'],
                     install_symlinks.InstallSymlinks(
                         '../foo',
                         self.tmpdir,
                         install_symlinks.MODE_MINI,
                         symlinks=FAKE_SYMLINKS))
    self.assertCountEqual(['minibin'], os.listdir(self.tmpdir))
    self.assertEqual('../foo/minibin',
                     os.readlink(os.path.join(self.tmpdir, 'minibin')))

  def testUninstallFull(self):
    self.testInstallFull()
    self.assertEqual(['fullbin', 'minibin'],
                     install_symlinks.UninstallSymlinks(
                         self.tmpdir,
                         install_symlinks.MODE_FULL,
                         symlinks=FAKE_SYMLINKS))
    self.assertCountEqual([], os.listdir(self.tmpdir))

  def testUninstallMini(self):
    self.testInstallFull()
    self.assertEqual(['minibin'],
                     install_symlinks.UninstallSymlinks(
                         self.tmpdir,
                         install_symlinks.MODE_MINI,
                         symlinks=FAKE_SYMLINKS))
    self.assertCountEqual(['fullbin'], os.listdir(self.tmpdir))


if __name__ == '__main__':
  unittest.main()
