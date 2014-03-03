#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands.update import ResourceUpdater
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
MINIMAL_UMPIRE_CONFIG = os.path.join(TEST_DIR, 'testdata',
                                     'minimal_empty_services_umpire.yaml')


class ResourceUpdaterTest(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    self.env.LoadConfig(custom_path=MINIMAL_UMPIRE_CONFIG)
    os.makedirs(self.env.resources_dir)

    # Create a fake factory_toolkit for test.
    self.fake_factory_toolkit_path = os.path.join(
        self.temp_dir, 'install_factory_toolkit.run')
    file_utils.WriteFile(self.fake_factory_toolkit_path, 'new factory toolkit')
    self.new_factory_toolkit_resource = (
        'install_factory_toolkit.run##78ddc759')

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def testUpdateInPlace(self):
    bundles = self.env.config['bundles']
    original_num_bundles = len(bundles)

    updater = ResourceUpdater(self.env)
    # No source_id: edit from default bundle.
    # No dest_id: in-place edit the source bundle.
    updater.Update([('factory_toolkit', self.fake_factory_toolkit_path)])

    # In-place bundle modification.
    self.assertEqual(2, original_num_bundles)
    default_bundle = bundles[1]

    self.assertEqual('default_test', default_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     default_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     default_bundle['resources']['server_factory_toolkit'])

  def testUpdateDestId(self):
    bundles = self.env.config['bundles']
    original_num_bundles = len(bundles)

    updater = ResourceUpdater(self.env)
    # No source_id: edit from default bundle.
    # dest_id: update source bundle and store in new bundle dest_id.
    updater.Update([('factory_toolkit', self.fake_factory_toolkit_path)],
                   dest_id='update_test')

    # Add a new bundle with updated component.
    self.assertEqual(original_num_bundles + 1, len(bundles))

    new_bundle = bundles[0]
    self.assertEqual('update_test', new_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     new_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     new_bundle['resources']['server_factory_toolkit'])

    default_bundle = bundles[2]
    self.assertEqual('default_test', default_bundle['id'])
    self.assertEqual('install_factory_toolkit.run##00000000',
                     default_bundle['resources']['device_factory_toolkit'])
    self.assertEqual('install_factory_toolkit.run##00000000',
                     default_bundle['resources']['server_factory_toolkit'])

  def testUpdateSourceId(self):
    bundles = self.env.config['bundles']
    original_num_bundles = len(bundles)

    updater = ResourceUpdater(self.env)
    # source_id: edit from specified bundle.
    # No dest_id: in-place edit the source bundle.
    updater.Update([('factory_toolkit', self.fake_factory_toolkit_path)],
                   source_id='non_default_test')

    # In-place bundle modification.
    self.assertEqual(original_num_bundles, len(bundles))

    target_bundle = bundles[0]
    self.assertEqual('non_default_test', target_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     target_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     target_bundle['resources']['server_factory_toolkit'])

  def testUpdateSourceIdDestId(self):
    bundles = self.env.config['bundles']
    original_num_bundles = len(bundles)

    updater = ResourceUpdater(self.env)
    # source_id: edit from specified bundle.
    # dest_id: update source bundle and store in new bundle dest_id.
    updater.Update([('factory_toolkit', self.fake_factory_toolkit_path)],
                   source_id='non_default_test',  dest_id='update_test')

    # Add a new bundle with updated component.
    self.assertEqual(original_num_bundles + 1, len(bundles))

    update_bundle = bundles[0]
    self.assertEqual('update_test', update_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     update_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     update_bundle['resources']['server_factory_toolkit'])

    source_bundle = bundles[1]
    self.assertEqual('non_default_test', source_bundle['id'])

    default_bundle = bundles[2]
    self.assertEqual('default_test', default_bundle['id'])

  def testUpdateBadSourceIdDestId(self):
    updater = ResourceUpdater(self.env)
    self.assertRaisesRegexp(
        UmpireError, 'Source bundle ID does not exist', updater.Update,
        [('factory_toolkit', self.fake_factory_toolkit_path)],
        source_id='not_exist')

    self.assertRaisesRegexp(
        UmpireError, 'Destination bundle ID already exists', updater.Update,
        [('factory_toolkit', self.fake_factory_toolkit_path)],
        dest_id='default_test')

  def testUpdateInvalidInput(self):
    updater = ResourceUpdater(self.env)
    self.assertRaisesRegexp(
        UmpireError, 'Unsupported resource type', updater.Update,
        [('unsupported', self.fake_factory_toolkit_path)])

    self.assertRaisesRegexp(
        UmpireError, 'Resource not found', updater.Update,
        [('factory_toolkit', os.path.join(self.temp_dir, 'not_exist'))])

  def testAllUpdatableResource(self):
    firmware_path = os.path.join(self.temp_dir, 'firmware.gz')
    file_utils.WriteFile(firmware_path, 'new firmware')
    new_firmware_resource = 'firmware.gz##f56ca36e'

    fsi_path = os.path.join(self.temp_dir, 'rootfs-release.gz')
    file_utils.WriteFile(fsi_path, 'new fsi')
    new_fsi_resource = 'rootfs-release.gz##932ecf09'

    hwid_path = os.path.join(self.temp_dir, 'hwid.gz')
    file_utils.WriteFile(hwid_path, 'new hwid')
    new_hwid_resource = 'hwid.gz##8c8fe9fe'

    updater = ResourceUpdater(self.env)
    updater.Update([
        ('factory_toolkit', self.fake_factory_toolkit_path),
        ('firmware', firmware_path),
        ('fsi', fsi_path),
        ('hwid', hwid_path)])

    bundle = self.env.config.GetDefaultBundle()
    self.assertEqual('default_test', bundle['id'])
    resources = bundle['resources']
    self.assertEqual(self.new_factory_toolkit_resource,
                     resources['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     resources['server_factory_toolkit'])
    self.assertEqual(new_firmware_resource, resources['firmware'])
    self.assertEqual(new_fsi_resource, resources['rootfs_release'])
    self.assertEqual(new_hwid_resource, resources['hwid'])



if __name__ == '__main__':
  unittest.main()
