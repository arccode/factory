#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import os
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools import get_version
from cros.factory.umpire.commands.update import ResourceUpdater
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.config import UmpireConfig
from cros.factory.umpire.umpire_env import UmpireEnvForTest
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(sys.modules[__name__].__file__)
TESTDATA_DIR = os.path.join(TEST_DIR, 'testdata')
MINIMAL_UMPIRE_CONFIG = os.path.join(TESTDATA_DIR,
                                     'minimal_empty_services_umpire.yaml')


class ResourceUpdaterTest(unittest.TestCase):
  def setUp(self):
    self.env = UmpireEnvForTest()
    self.env.LoadConfig(custom_path=MINIMAL_UMPIRE_CONFIG)

    # Create a fake factory_toolkit for test.
    self.fake_factory_toolkit_path = os.path.join(
        self.env.base_dir, 'install_factory_toolkit.run')
    file_utils.WriteFile(self.fake_factory_toolkit_path, 'new factory toolkit')
    self.new_factory_toolkit_resource = (
        'install_factory_toolkit.run##78ddc759')

  def testUpdateInPlace(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = ResourceUpdater(self.env)
    # No source_id: edit from default bundle.
    # No dest_id: in-place edit the source bundle.
    updated_config_path = updater.Update(
        [('factory_toolkit', self.fake_factory_toolkit_path)])
    updated_bundles = UmpireConfig(updated_config_path)['bundles']

    # In-place bundle modification.
    self.assertEqual(num_bundles_before_update, len(updated_bundles))
    default_bundle = updated_bundles[1]

    self.assertEqual('default_test', default_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     default_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     default_bundle['resources']['server_factory_toolkit'])

  def testUpdateDestId(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = ResourceUpdater(self.env)
    # No source_id: edit from default bundle.
    # dest_id: update source bundle and store in new bundle dest_id.
    updated_config_path = updater.Update(
        [('factory_toolkit', self.fake_factory_toolkit_path)],
        dest_id='update_test')
    updated_bundles = UmpireConfig(updated_config_path)['bundles']

    # Add a new bundle with updated component.
    self.assertEqual(num_bundles_before_update + 1, len(updated_bundles))

    new_bundle = updated_bundles[0]
    self.assertEqual('update_test', new_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     new_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     new_bundle['resources']['server_factory_toolkit'])

    default_bundle = updated_bundles[2]
    self.assertEqual('default_test', default_bundle['id'])
    self.assertEqual('install_factory_toolkit.run##d41d8cd9',
                     default_bundle['resources']['device_factory_toolkit'])
    self.assertEqual('install_factory_toolkit.run##d41d8cd9',
                     default_bundle['resources']['server_factory_toolkit'])

  def testUpdateSourceId(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = ResourceUpdater(self.env)
    # source_id: edit from specified bundle.
    # No dest_id: in-place edit the source bundle.
    updated_config_path = updater.Update(
        [('factory_toolkit', self.fake_factory_toolkit_path)],
        source_id='non_default_test')
    updated_bundles = UmpireConfig(updated_config_path)['bundles']

    # In-place bundle modification.
    self.assertEqual(num_bundles_before_update, len(updated_bundles))

    target_bundle = updated_bundles[0]
    self.assertEqual('non_default_test', target_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     target_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     target_bundle['resources']['server_factory_toolkit'])

  def testUpdateSourceIdDestId(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = ResourceUpdater(self.env)
    # source_id: edit from specified bundle.
    # dest_id: update source bundle and store in new bundle dest_id.
    updated_config_path = updater.Update(
        [('factory_toolkit', self.fake_factory_toolkit_path)],
        source_id='non_default_test',  dest_id='update_test')
    updated_bundles = UmpireConfig(updated_config_path)['bundles']

    # Add a new bundle with updated component.
    self.assertEqual(num_bundles_before_update + 1, len(updated_bundles))

    update_bundle = updated_bundles[0]
    self.assertEqual('update_test', update_bundle['id'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     update_bundle['resources']['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     update_bundle['resources']['server_factory_toolkit'])

    source_bundle = updated_bundles[1]
    self.assertEqual('non_default_test', source_bundle['id'])

    default_bundle = updated_bundles[2]
    self.assertEqual('default_test', default_bundle['id'])

  def testUpdateStagingFileExists(self):
    self.env.StageConfigFile(self.env.config_path)
    self.assertRaisesRegexp(
        UmpireError, 'Cannot update resources as staging config exists.',
        ResourceUpdater, self.env)

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
        [('factory_toolkit', os.path.join(self.env.base_dir, 'not_exist'))])

  def testAllUpdatableResource(self):
    mox_obj = mox.Mox()
    BIOS_VERSION = 'bios_0.0.1'
    EC_VERSION = 'ec_0.0.2'
    FSI_VERSION = '0.0.1'

    firmware_path = os.path.join(self.env.base_dir, 'firmware.gz')
    file_utils.WriteFile(firmware_path, 'new firmware')
    new_firmware_resource = 'firmware.gz#%s:%s#f56ca36e' % (
        BIOS_VERSION, EC_VERSION)

    fsi_path = os.path.join(self.env.base_dir, 'rootfs-release.gz')
    file_utils.WriteFile(fsi_path, 'new fsi')
    new_fsi_resource = 'rootfs-release.gz#%s#932ecf09' % FSI_VERSION

    # HWID version extracted from hwid.gz's checksum field.
    hwid_path = os.path.join(TESTDATA_DIR, 'hwid.gz')
    new_hwid_resource = ('hwid.gz#a95cd8def470df2e7a8d549af887897e2d095bb0'
                         '#061d5528')

    # TODO(deanliao): use real firmware.gz/rootfs-release.gz in which
    #     Umpire can extract version from.
    mox_obj.StubOutWithMock(
        get_version, 'GetFirmwareVersionsFromOmahaChannelFile')
    mox_obj.StubOutWithMock(
          get_version, 'GetReleaseVersionFromOmahaChannelFile')

    get_version.GetFirmwareVersionsFromOmahaChannelFile(
        firmware_path).AndReturn((BIOS_VERSION, EC_VERSION))
    get_version.GetReleaseVersionFromOmahaChannelFile(
          fsi_path, no_root=True).AndReturn(FSI_VERSION)

    mox_obj.ReplayAll()

    updater = ResourceUpdater(self.env)
    updated_config_path = updater.Update([
        ('factory_toolkit', self.fake_factory_toolkit_path),
        ('firmware', firmware_path),
        ('fsi', fsi_path),
        ('hwid', hwid_path)])
    updated_bundle = UmpireConfig(updated_config_path).GetDefaultBundle()

    self.assertEqual('default_test', updated_bundle['id'])
    resources = updated_bundle['resources']
    self.assertEqual(self.new_factory_toolkit_resource,
                     resources['device_factory_toolkit'])
    self.assertEqual(self.new_factory_toolkit_resource,
                     resources['server_factory_toolkit'])
    self.assertEqual(new_firmware_resource, resources['firmware'])
    self.assertEqual(new_fsi_resource, resources['rootfs_release'])
    self.assertEqual(new_hwid_resource, resources['hwid'])

    mox_obj.UnsetStubs()
    mox_obj.VerifyAll()


if __name__ == '__main__':
  unittest.main()
