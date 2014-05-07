#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for installer.py."""


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

    # True if we are pretending to be running inside CrOS.  This will
    # cause a fake /etc/lsb-release file to be returned.
    self._in_cros = None
    installer.FactoryToolkitInstaller._ReadLSBRelease = (
      lambda _: 'CHROMEOS_RELEASE' if self._in_cros else None)

  def tearDown(self):
    shutil.rmtree(self.src)
    shutil.rmtree(self.dest)

  def makeStatefulPartition(self):
    os.makedirs(os.path.join(self.dest, 'dev_image'))
    os.makedirs(os.path.join(self.dest, 'var_overlay'))

  def makeLiveDevice(self):
    os.makedirs(os.path.join(self.dest, 'usr/local'))
    os.makedirs(os.path.join(self.dest, 'var'))

  def createInstaller(self, enabled_tag=True, system_root='/'):
    self._installer = installer.FactoryToolkitInstaller(
        self.src, self.dest, not enabled_tag, system_root=system_root)
    self._installer._sudo = False

  def testNonRoot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 9999 # Not root
    self._in_cros = True
    self.assertRaises(Exception, self.createInstaller, True, self.dest)

  def testInChroot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0 # root
    self.assertRaises(SystemExit, self.createInstaller, True, self.dest)

  def testInstall(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0 # root
    self._in_cros = True
    self.createInstaller(system_root=self.dest)
    self._installer.Install()
    with open(os.path.join(self.dest, 'usr/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))

  def testIncorrectPatch(self):
    with self.assertRaises(Exception):
      self.createInstaller()

  def testPatch(self):
    self.makeStatefulPartition()
    self.createInstaller()
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
    self._in_cros = True
    self.createInstaller(enabled_tag=False, system_root=self.dest)
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
