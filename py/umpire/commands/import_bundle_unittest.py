#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import os
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
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


class LoadBundleManifestTest(unittest.TestCase):
  def setUp(self):
    self.bundle = FactoryBundle()

  def testLoadNormally(self):
    self.bundle.Load(TEST_BUNDLE_DIR)

  def testMissingRelease(self):
    self.assertRaisesRegexp(
        UmpireError, 'Image type not found: release',
        self.bundle.Load, TEST_BUNDLE_MISSING_RELEASE_DIR)

  def testYamlError(self):
    with file_utils.TempDirectory() as bundle_dir:
      file_utils.WriteFile(os.path.join(bundle_dir, 'MANIFEST.yaml'),
                           'illformed: yaml: file:')
      self.assertRaisesRegexp(UmpireError, 'Failed to load MANIFEST.yaml',
                              self.bundle.Load, bundle_dir)


class testImportBundle(unittest.TestCase):
  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.env = UmpireEnv()
    self.env.base_dir = self.temp_dir
    # TODO(deanliao): replace with real UmpireConfig once its validator
    #     is ready.
    self.env.config = {'board': 'daisy_spring'}
    os.makedirs(self.env.resources_dir)

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def testImport(self):
    importer = BundleImporter(self.env)
    # Inject timestamp so that download conf can be compared easily.
    importer._timestamp = datetime.datetime(2014, 1, 1, 0, 0)

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
        'server_factory_toolkit': 'install_factory_toolkit.run##',
        'device_factory_toolkit': 'install_factory_toolkit.run##',
        'netboot_kernel': 'vmlinux.uimg##d41d8cd9',
        'complete_script': 'complete.gz##d41d8cd9',
        'efi_partition': 'efi.gz##d41d8cd9',
        'firmware': 'firmware.gz##d41d8cd9',
        'hwid': 'hwid.gz##d41d8cd9',
        'oem_partition': 'oem.gz##d41d8cd9',
        'rootfs_release': 'rootfs-release.gz##d41d8cd9',
        'rootfs_test': 'rootfs-test.gz##d41d8cd9',
        'stateful_partition': 'state.gz##d41d8cd9',
        'download_conf': 'daisy_spring.conf##'}
    self.assertSetEqual(set(expect_resources), set(resources))
    for key, value in expect_resources.items():
      self.assertTrue(resources[key].startswith(value))

    # Verify download config.
    expect_download_conf = file_utils.ReadLines(DOWNLOAD_CONFIG_PATH)
    download_conf = file_utils.ReadLines(
        self.env.GetResourcePath(resources['download_conf']))
    # Skip first two as bundle path might change based on the path
    # running the unittest.
    self.assertListEqual(expect_download_conf[2:], download_conf[2:])

  def testImportHashCollision(self):
    # Create hash collision files (same hash but different content).
    dup_factory_toolkit = self.env.GetResourcePath(
        'install_factory_toolkit.run##7509337e', check=False)
    file_utils.WriteFile(dup_factory_toolkit, 'not a factory toolkit')
    dup_netboot_image = self.env.GetResourcePath('vmlinux.uimg##d41d8cd9',
                                                 check=False)
    file_utils.WriteFile(dup_netboot_image, 'not a netboot image')

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
