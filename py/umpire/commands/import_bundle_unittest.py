#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import mox
import os
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools import get_version
from cros.factory.umpire.commands.import_bundle import (BundleImporter,
                                                        FactoryBundle)
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils import file_utils

TESTDATA_DIR = os.path.join(os.path.dirname(sys.modules[__name__].__file__),
                            'testdata')
TEST_BUNDLE_DIR = os.path.join(TESTDATA_DIR, 'bundle_for_import')
TEST_BUNDLE_MISSING_RELEASE_DIR = os.path.join(TESTDATA_DIR,
                                               'bundle_missing_release_image')
DOWNLOAD_CONFIG_PATH = os.path.join(TESTDATA_DIR, 'download_for_import.conf')

# MD5 and unpacked content of factory_toolkit:
#   TEST_BUNDLE_DIR/factory_test/install_factory_toolkit.run
TOOLKIT_MD5 = '7509337e'
UMPIRE_RELATIVE_PATH = os.path.join('usr', 'local', 'factory', 'bin', 'umpire')


class LoadBundleManifestTest(unittest.TestCase):
  def setUp(self):
    self.bundle = FactoryBundle()

  def testLoadNormally(self):
    self.bundle.Load(TEST_BUNDLE_DIR)

  # TODO(deanliao): figure out if mandatory image check is necessary.
  # Temporary remove the check.
  # def testMissingRelease(self):
  #   self.assertRaisesRegexp(
  #       UmpireError, 'Image type not found: release',
  #       self.bundle.Load, TEST_BUNDLE_MISSING_RELEASE_DIR)

  def testYamlError(self):
    with file_utils.TempDirectory() as bundle_dir:
      file_utils.WriteFile(os.path.join(bundle_dir, 'MANIFEST.yaml'),
                           'illformed: yaml: file:')
      self.assertRaisesRegexp(UmpireError, 'Failed to load MANIFEST.yaml',
                              self.bundle.Load, bundle_dir)


BIOS_VERSION = 'bios_0.0.1'
EC_VERSION = 'ec_0.0.2'
FSI_VERSION = '0.0.3'
TEST_IMAGE_VERSION = '0.0.4'


class testImportBundle(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.temp_dir = tempfile.mkdtemp()
    self.env = UmpireEnv()
    self.env.base_dir = self.temp_dir
    # TODO(deanliao): replace with real UmpireConfig once its validator
    #     is ready.
    self.env.config = {'board': 'daisy_spring'}
    os.makedirs(self.env.resources_dir)

  def tearDown(self):
    shutil.rmtree(self.temp_dir)
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def MockOutGetVersion(self):
    # TODO(deanliao): use real firmware.gz/rootfs-release.gz in which
    #     Umpire can extract version from.
    self.mox.StubOutWithMock(
        get_version, 'GetFirmwareVersionsFromOmahaChannelFile')
    self.mox.StubOutWithMock(
          get_version, 'GetReleaseVersionFromOmahaChannelFile')

    # pylint: disable=E1101
    get_version.GetFirmwareVersionsFromOmahaChannelFile(
        mox.StrContains('firmware.gz')).MultipleTimes().AndReturn(
            (BIOS_VERSION, EC_VERSION))
    get_version.GetReleaseVersionFromOmahaChannelFile(
        mox.StrContains('rootfs-release.gz')).MultipleTimes().AndReturn(
            FSI_VERSION)
    get_version.GetReleaseVersionFromOmahaChannelFile(
        mox.StrContains('rootfs-test.gz')).MultipleTimes().AndReturn(
            TEST_IMAGE_VERSION)

  def testImport(self):
    importer = BundleImporter(self.env)
    # Inject timestamp so that download conf can be compared easily.
    importer._timestamp = datetime.datetime(2014, 1, 1, 0, 0)

    self.MockOutGetVersion()
    self.mox.ReplayAll()

    importer.Import(TEST_BUNDLE_DIR, 'test_bundle')

    # Verify newly added ruleset.
    self.assertEqual(1, len(self.env.config['rulesets']))
    self.assertDictEqual(
        {'bundle_id': 'test_bundle',
         'note': 'Please update match rule in ruleset',
         'active': False},
        self.env.config['rulesets'][0])

    # Verify newly added bundle.
    self.assertEqual(1, len(self.env.config['bundles']))
    bundle = self.env.config['bundles'][0]
    self.assertEqual('test_bundle', bundle['id'])
    self.assertIn('shop_floor', bundle)
    self.assertEqual('cros.factory.shopfloor.daisy_spring_shopfloor',
                     bundle['shop_floor']['handler'])

    # Verify resources section using startswith().
    self.assertIn('resources', bundle)
    resources = bundle['resources']

    # Note that download_conf's filename starts with "daisy_spring",
    # which is board name specified in UmpireEnv.
    expect_resources = {
        'server_factory_toolkit': 'install_factory_toolkit.run##' + TOOLKIT_MD5,
        'device_factory_toolkit': 'install_factory_toolkit.run##' + TOOLKIT_MD5,
        'netboot_vmlinux': 'vmlinux.uimg##d41d8cd9',
        'complete_script': 'complete.gz##d41d8cd9',
        'efi_partition': 'efi.gz##d41d8cd9',
        'firmware': 'firmware.gz#%s:%s#d41d8cd9' % (BIOS_VERSION, EC_VERSION),
        'hwid': 'hwid.gz##d41d8cd9',
        'oem_partition': 'oem.gz##d41d8cd9',
        'rootfs_release': 'rootfs-release.gz#%s#d41d8cd9' % FSI_VERSION,
        'rootfs_test': 'rootfs-test.gz#%s#d41d8cd9' % TEST_IMAGE_VERSION,
        'stateful_partition': 'state.gz##d41d8cd9',
        'download_conf': 'daisy_spring.conf##'}
    self.assertSetEqual(set(expect_resources), set(resources))
    for key, value in expect_resources.items():
      self.assertTrue(resources[key].startswith(value))

    # Verify that device toolkit is unpacked.
    expected_device_toolkit = os.path.join(self.env.device_toolkits_dir,
                                           TOOLKIT_MD5)
    self.assertTrue(os.path.isdir(expected_device_toolkit))
    self.assertTrue(os.path.exists(os.path.join(expected_device_toolkit,
                                                UMPIRE_RELATIVE_PATH)))

    # Verify download config.
    expect_download_conf = file_utils.ReadLines(DOWNLOAD_CONFIG_PATH)
    download_conf = file_utils.ReadLines(
        self.env.GetResourcePath(resources['download_conf']))
    # Skip first two as bundle path might change based on the path
    # running the unittest.
    self.maxDiff = None
    self.assertListEqual(sorted(expect_download_conf[2:]),
                         sorted(download_conf[2:]))

  def testImportSkipUnpackExistingToolkitDir(self):
    importer = BundleImporter(self.env)

    # Create unpacked device toolkit directory first.
    device_toolkit_dir = os.path.join(self.env.device_toolkits_dir,
                                      TOOLKIT_MD5)
    os.makedirs(device_toolkit_dir)

    self.MockOutGetVersion()
    self.mox.ReplayAll()

    importer.Import(TEST_BUNDLE_DIR, 'test_bundle')

    # Verify that toolkit is not unpacked.
    self.assertFalse(os.path.exists(os.path.join(device_toolkit_dir,
                                                 UMPIRE_RELATIVE_PATH)))

  def testImportHashCollision(self):
    # Create hash collision files (same hash but different content).
    dup_factory_toolkit = self.env.GetResourcePath(
        'install_factory_toolkit.run##7509337e', check=False)
    file_utils.WriteFile(dup_factory_toolkit, 'not a factory toolkit')
    dup_netboot_image = self.env.GetResourcePath('vmlinux.uimg##d41d8cd9',
                                                 check=False)
    file_utils.WriteFile(dup_netboot_image, 'not a netboot image')

    self.MockOutGetVersion()
    self.mox.ReplayAll()

    importer = BundleImporter(self.env)
    self.assertRaisesRegexp(UmpireError, 'Found 2 hash collision',
                            importer.Import, TEST_BUNDLE_DIR, 'test_bundle')


  def testImportBundleIdCollision(self):
    self.env.config['bundles'] = [{'id': 'bundleA'}]
    importer = BundleImporter(self.env)
    self.assertRaisesRegexp(UmpireError,
                            "bundle_id: 'bundleA' already in use",
                            importer.Import, TEST_BUNDLE_DIR, 'bundleA')

  def testImportDifferentBoardName(self):
    self.env.config['board'] = 'not_a_daisy_spring'

    importer = BundleImporter(self.env)
    self.assertRaisesRegexp(UmpireError,
                            'Board mismatch',
                            importer.Import, TEST_BUNDLE_DIR, 'test_bundle')


if __name__ == '__main__':
  unittest.main()
