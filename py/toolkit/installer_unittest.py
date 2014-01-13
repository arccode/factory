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

  def tearDown(self):
    shutil.rmtree(self.src)
    shutil.rmtree(self.dest)

  def makeStatefulPartition(self):
    os.makedirs(os.path.join(self.dest, 'dev_image/local'))
    os.makedirs(os.path.join(self.dest, 'var_overlay'))

  def makeLiveDevice(self):
    os.makedirs(os.path.join(self.dest, 'usr/local'))
    os.makedirs(os.path.join(self.dest, 'var'))

  def createInstaller(self, patch_test_image=False):
    args = argparse.Namespace()
    args.dest = self.dest
    args.patch_test_image = patch_test_image
    self._installer = installer.FactoryToolkitInstaller(self.src, args)

  def testNonRoot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 9999 # Not root
    self.assertRaises(Exception, self.createInstaller)

  def testInChroot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0 # root
    old_path_exists = os.path.exists
    def patchedExists(x):
      if x == '/etc/lsb-release':
        return False
      return old_path_exists(x)
    os.path.exists = patchedExists
    self.assertRaises(Exception, self.createInstaller)

  def testInstall(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0 # root
    old_path_exists = os.path.exists
    def patchedExists(x):
      if x == '/etc/lsb-release':
        return True
      return old_path_exists(x)
    os.path.exists = patchedExists
    self.createInstaller()
    self._installer.Install()
    with open(os.path.join(self.dest, 'usr/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))

  def testIncorrectPatch(self):
    self.assertRaises(Exception, self.createInstaller, True)

  def testPatch(self):
    self.makeStatefulPartition()
    self.createInstaller(patch_test_image=True)
    self._installer.Install()
    with open(os.path.join(self.dest, 'dev_image/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var_overlay', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'dev_image/local/factory/enabled')))


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  unittest.main()
