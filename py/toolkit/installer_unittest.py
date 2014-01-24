#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for installer.py."""


import argparse
import factory_common  # pylint: disable=W0611
import logging
import os
import shutil
import tempfile
import unittest

from cros.factory.toolkit import installer


class ToolkitInstallerTest(unittest.TestCase):
  """Test factory toolkit installer."""
  def setUp(self):
    self.src = tempfile.mkdtemp(prefix='ToolkitInstallerTest.')
    os.makedirs(os.path.join(self.src, 'usr/local/factory'))
    os.makedirs(os.path.join(self.src, 'var'))
    with open(os.path.join(self.src, 'usr/local', 'file1'), 'w') as f:
      f.write('install me!')
    with open(os.path.join(self.src, 'var', 'log1'), 'w') as f:
      f.write('I am a log file!')

    self.dest = tempfile.mkdtemp(prefix='ToolkitInstallerTest.')
    self._installer = None

    self._lsb_release_exists = None
    old_path_exists = os.path.exists
    def patchedExists(x):
      if self._lsb_release_exists is not None and x == '/etc/lsb-release':
        return self._lsb_release_exists
      return old_path_exists(x)
    os.path.exists = patchedExists

  def tearDown(self):
    shutil.rmtree(self.src)
    shutil.rmtree(self.dest)

  def makeStatefulPartition(self):
    os.makedirs(os.path.join(self.dest, 'dev_image'))
    os.makedirs(os.path.join(self.dest, 'var_overlay'))

  def makeLiveDevice(self):
    os.makedirs(os.path.join(self.dest, 'usr/local'))
    os.makedirs(os.path.join(self.dest, 'var'))

  def createInstaller(self, patch_test_image=False, enabled_tag=True):
    args = argparse.Namespace()
    args.dest = self.dest
    args.patch_test_image = patch_test_image
    args.no_enable = not enabled_tag
    self._installer = installer.FactoryToolkitInstaller(self.src, args)

  def testNonRoot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 9999 # Not root
    self._lsb_release_exists = None
    self.assertRaises(Exception, self.createInstaller)

  def testInChroot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0 # root
    self._lsb_release_exists = False
    self.assertRaises(Exception, self.createInstaller)

  def testInstall(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0 # root
    self._lsb_release_exists = True
    self.createInstaller()
    self._installer.Install()
    with open(os.path.join(self.dest, 'usr/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))

  def testIncorrectPatch(self):
    self._lsb_release_exists = None
    with self.assertRaises(Exception):
      self.createInstaller(patch_test_image=True)

  def testPatch(self):
    self.makeStatefulPartition()
    self._lsb_release_exists = None
    self.createInstaller(patch_test_image=True)
    self._installer.Install()
    with open(os.path.join(self.dest, 'dev_image', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var_overlay', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'dev_image/factory/enabled')))

  def testNoEnable(self):
    self.makeLiveDevice()
    os.makedirs(os.path.join(self.dest, 'usr/local/factory'))
    with open(os.path.join(self.dest, 'usr/local/factory/enabled'), 'w') as f:
      pass
    os.getuid = lambda: 0 # root
    self._lsb_release_exists = True
    self.createInstaller(enabled_tag=False)
    self._installer.Install()
    with open(os.path.join(self.dest, 'usr/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertFalse(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  unittest.main()
