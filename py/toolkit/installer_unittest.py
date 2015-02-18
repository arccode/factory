#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for installer.py."""


from __future__ import print_function
import factory_common  # pylint: disable=W0611
import logging
import os
import shutil
import tempfile
import unittest

from cros.factory.toolkit import installer


class ToolkitInstallerTest(unittest.TestCase):
  """Test factory toolkit installer."""
  FILES = [
      ('usr/local/file1', 'install me!'),
      ('var/log1', 'I am a log file!'),
      ('usr/local/factory/py/umpire/__init__.py', 'This goes to DUT!'),
      ('usr/local/factory/py/umpire/client/umpire_client.py',
       'This goes to DUT, too!'),
      ('usr/local/factory/py/umpire/archiver.py',
       'I only run on Umpire server!'),
  ]

  def setUp(self):
    self.src = tempfile.mkdtemp(prefix='ToolkitInstallerTest.')
    os.makedirs(os.path.join(self.src, 'usr/local/factory/init'))
    os.makedirs(os.path.join(self.src, 'var/factory/state'))
    os.makedirs(os.path.join(self.src, 'usr/local/factory/py/umpire/client'))

    for install_file in self.FILES:
      with open(os.path.join(self.src, install_file[0]), 'w') as f:
        f.write(install_file[1])

    self.dest = tempfile.mkdtemp(prefix='ToolkitInstallerTest.')
    self._installer = None

    # True if we are pretending to be running inside CrOS.
    self._override_in_cros_device = False
    # pylint: disable=W0212
    installer._in_cros_device = lambda: self._override_in_cros_device

  def tearDown(self):
    shutil.rmtree(self.src)
    shutil.rmtree(self.dest)

  def makeStatefulPartition(self):
    os.makedirs(os.path.join(self.dest, 'dev_image'))
    os.makedirs(os.path.join(self.dest, 'var_overlay'))

  def makeLiveDevice(self):
    os.makedirs(os.path.join(self.dest, 'usr/local'))
    os.makedirs(os.path.join(self.dest, 'var'))

  def createInstaller(self, enabled_tag=True, system_root='/',
                      enable_presenter=True, enable_device=False,
                      non_cros=False):
    self._installer = installer.FactoryToolkitInstaller(
        self.src, self.dest, not enabled_tag, enable_presenter,
        enable_device, non_cros=non_cros,
        system_root=system_root)
    self._installer._sudo = False # pylint: disable=W0212

  def testNonRoot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 9999  # Not root
    self._override_in_cros_device = True
    self.assertRaises(Exception, self.createInstaller, True, self.dest)

  def testInChroot(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0  # root
    self.assertRaises(SystemExit, self.createInstaller, True, self.dest)

  def installLiveDevice(self):
    self._installer.Install()
    with open(os.path.join(self.dest, 'usr/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/init/run_goofy_presenter')))
    self.assertFalse(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/init/run_goofy_device')))
    self.assertEquals(
        '../factory/bin/gooftool',
        os.readlink(os.path.join(self.dest, 'usr/local/bin/gooftool')))
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/py/umpire/__init__.py')))
    self.assertTrue(os.path.exists(
        os.path.join(self.dest,
                     'usr/local/factory/py/umpire/client/umpire_client.py')))
    self.assertFalse(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/py/umpire/archiver.py')))

  def testNonCrosInstaller(self):
    self.makeLiveDevice()
    self.createInstaller(non_cros=True, system_root=self.dest)
    self.installLiveDevice()

  def testInstall(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0  # root
    self._override_in_cros_device = True
    self.createInstaller(system_root=self.dest)
    self.installLiveDevice()

  def testDeviceOnly(self):
    self.makeLiveDevice()
    os.getuid = lambda: 0  # root
    self._override_in_cros_device = True
    self.createInstaller(system_root=self.dest,
                         enable_presenter=False, enable_device=True)
    self._installer.Install()
    self.assertFalse(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/init/run_goofy_presenter')))
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/init/run_goofy_device')))

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
    os.getuid = lambda: 0  # root
    self._override_in_cros_device = True
    self.createInstaller(enabled_tag=False, system_root=self.dest)
    self._installer.Install()
    with open(os.path.join(self.dest, 'usr/local', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
    with open(os.path.join(self.dest, 'var', 'log1'), 'r') as f:
      self.assertEqual(f.read(), 'I am a log file!')
    self.assertFalse(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
