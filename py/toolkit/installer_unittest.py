#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for installer.py."""


from __future__ import print_function

import logging
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.toolkit import installer


class ToolkitInstallerTest(unittest.TestCase):
  """Test factory toolkit installer."""
  FILES = [
      ('usr/local/file1', 'install me!'),
      ('usr/local/factory/py/umpire/__init__.py', 'This goes to DUT!'),
      ('usr/local/factory/py/umpire/client/umpire_client.py',
       'This goes to DUT, too!'),
      ('usr/local/factory/py/umpire/archiver.py',
       'I only run on Umpire server!'),
      ('usr/local/factory/init/main.d/a.sh',
       'This is a.sh'),
      ('usr/local/factory/init/main.d/b.sh',
       'This is b.sh'),
  ]

  def setUp(self):
    self.src = tempfile.mkdtemp(prefix='ToolkitInstallerTest.')
    os.makedirs(os.path.join(self.src, 'usr/local/factory/init/main.d'))
    os.makedirs(os.path.join(self.src, 'usr/local/factory/py/umpire/client'))

    for install_file in self.FILES:
      with open(os.path.join(self.src, install_file[0]), 'w') as f:
        f.write(install_file[1])

    self.dest = tempfile.mkdtemp(prefix='ToolkitInstallerTest.')
    self._installer = None

    # True if we are pretending to be running inside CrOS.
    self._override_in_cros_device = False
    # pylint: disable=protected-access
    installer.sys_utils.InCrOSDevice = lambda: self._override_in_cros_device

  def tearDown(self):
    shutil.rmtree(self.src)
    shutil.rmtree(self.dest)

  def makeStatefulPartition(self):
    os.makedirs(os.path.join(self.dest, 'dev_image'))

  def makeLiveDevice(self):
    os.makedirs(os.path.join(self.dest, 'usr/local'))

  def createInstaller(self, enabled_tag=True, system_root='/',
                      non_cros=False, apps=None):
    self._installer = installer.FactoryToolkitInstaller(
        self.src, self.dest, not enabled_tag, non_cros=non_cros,
        system_root=system_root, apps=apps)
    self._installer._sudo = False  # pylint: disable=protected-access

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
    self.assertTrue(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))
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
    self.createInstaller(system_root=self.dest)
    self._installer.Install()

  def testIncorrectPatch(self):
    with self.assertRaises(Exception):
      self.createInstaller()

  def testPatch(self):
    self.makeStatefulPartition()
    self.createInstaller()
    self._installer.Install()
    with open(os.path.join(self.dest, 'dev_image', 'file1'), 'r') as f:
      self.assertEqual(f.read(), 'install me!')
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
    self.assertFalse(os.path.exists(
        os.path.join(self.dest, 'usr/local/factory/enabled')))

  def testEnableApp(self):
    self.makeLiveDevice()
    os.makedirs(os.path.join(self.dest, 'usr/local/factory/init/main.d'))
    os.getuid = lambda: 0  # root
    self._override_in_cros_device = True
    self.createInstaller(system_root=self.dest, apps=['+a', '-b'])
    self._installer.Install()

    self.assertTrue(os.path.exists(os.path.join(
        self.dest, 'usr/local/factory/init/main.d/enable-a')))
    self.assertFalse(os.path.exists(os.path.join(
        self.dest, 'usr/local/factory/init/main.d/disable-a')))
    self.assertFalse(os.path.exists(os.path.join(
        self.dest, 'usr/local/factory/init/main.d/enable-b')))
    self.assertTrue(os.path.exists(os.path.join(
        self.dest, 'usr/local/factory/init/main.d/disable-b')))

  def testEnableAppWrongFormat(self):
    self.makeLiveDevice()
    os.makedirs(os.path.join(self.dest, 'usr/local/factory/init/main.d'))
    os.getuid = lambda: 0  # root
    self._override_in_cros_device = True
    self.createInstaller(system_root=self.dest, apps=['a', '-b'])

    with self.assertRaises(ValueError):
      self._installer.Install()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
