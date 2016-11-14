#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import gzip
import mox
import os
import subprocess
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools import get_version
from cros.factory.umpire.commands import update
from cros.factory.umpire import common
from cros.factory.umpire import config
from cros.factory.umpire import umpire_env
from cros.factory.utils import file_utils


TEST_DIR = os.path.dirname(__file__)
TESTDATA_DIR = os.path.join(TEST_DIR, 'testdata')
MINIMAL_UMPIRE_CONFIG = os.path.join(TESTDATA_DIR,
                                     'minimal_empty_services_umpire.yaml')
# Use a real mimic install_factory_toolkit.run in upper level's testdata.
UPPERLEVEL_TESTDATA_DIR = os.path.join(TEST_DIR, '..', 'testdata')
FACTORY_TOOLKIT_DIR = os.path.join(UPPERLEVEL_TESTDATA_DIR,
                                   'install_factory_toolkit.run')
FACTORY_TOOLKIT_RES = 'install_factory_toolkit.run##7509337e'


class ResourceUpdaterTest(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnvForTest()
    self.env.LoadConfig(custom_path=MINIMAL_UMPIRE_CONFIG)

  def testUpdateInPlace(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = update.ResourceUpdater(self.env)
    # No source_id: edit from default bundle.
    # No dest_id: in-place edit the source bundle.
    updated_config_path = updater.Update([('factory_toolkit',
                                           FACTORY_TOOLKIT_DIR)])
    updated_bundles = config.UmpireConfig(updated_config_path)['bundles']

    # In-place bundle modification.
    self.assertEqual(num_bundles_before_update, len(updated_bundles))
    default_bundle = updated_bundles[1]

    self.assertEqual('default_test', default_bundle['id'])
    self.assertEqual(FACTORY_TOOLKIT_RES,
                     default_bundle['resources']['device_factory_toolkit'])

  def testUpdateDestId(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = update.ResourceUpdater(self.env)
    # No source_id: edit from default bundle.
    # dest_id: update source bundle and store in new bundle dest_id.
    updated_config_path = updater.Update(
        [('factory_toolkit', FACTORY_TOOLKIT_DIR)],
        dest_id='update_test')
    updated_bundles = config.UmpireConfig(updated_config_path)['bundles']

    # Add a new bundle with updated component.
    self.assertEqual(num_bundles_before_update + 1, len(updated_bundles))

    new_bundle = updated_bundles[0]
    self.assertEqual('update_test', new_bundle['id'])
    self.assertEqual(FACTORY_TOOLKIT_RES,
                     new_bundle['resources']['device_factory_toolkit'])

    default_bundle = updated_bundles[2]
    self.assertEqual('default_test', default_bundle['id'])
    self.assertEqual('install_factory_toolkit.run##d41d8cd9',
                     default_bundle['resources']['device_factory_toolkit'])

  def testUpdateSourceId(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = update.ResourceUpdater(self.env)
    # source_id: edit from specified bundle.
    # No dest_id: in-place edit the source bundle.
    updated_config_path = updater.Update(
        [('factory_toolkit', FACTORY_TOOLKIT_DIR)],
        source_id='non_default_test')
    updated_bundles = config.UmpireConfig(updated_config_path)['bundles']

    # In-place bundle modification.
    self.assertEqual(num_bundles_before_update, len(updated_bundles))

    target_bundle = updated_bundles[0]
    self.assertEqual('non_default_test', target_bundle['id'])
    self.assertEqual(FACTORY_TOOLKIT_RES,
                     target_bundle['resources']['device_factory_toolkit'])

  def testUpdateSourceIdDestId(self):
    num_bundles_before_update = len(self.env.config['bundles'])

    updater = update.ResourceUpdater(self.env)
    # source_id: edit from specified bundle.
    # dest_id: update source bundle and store in new bundle dest_id.
    updated_config_path = updater.Update(
        [('factory_toolkit', FACTORY_TOOLKIT_DIR)],
        source_id='non_default_test', dest_id='update_test')
    updated_bundles = config.UmpireConfig(updated_config_path)['bundles']

    # Add a new bundle with updated component.
    self.assertEqual(num_bundles_before_update + 1, len(updated_bundles))

    update_bundle = updated_bundles[0]
    self.assertEqual('update_test', update_bundle['id'])
    self.assertEqual(FACTORY_TOOLKIT_RES,
                     update_bundle['resources']['device_factory_toolkit'])

    source_bundle = updated_bundles[1]
    self.assertEqual('non_default_test', source_bundle['id'])

    default_bundle = updated_bundles[2]
    self.assertEqual('default_test', default_bundle['id'])

  def testUpdateStagingFileExists(self):
    self.env.StageConfigFile(self.env.config_path)
    self.assertRaisesRegexp(
        common.UmpireError, 'Cannot update resources as staging config exists.',
        update.ResourceUpdater, self.env)

  def testUpdateBadSourceIdDestId(self):
    updater = update.ResourceUpdater(self.env)
    self.assertRaisesRegexp(
        common.UmpireError, 'Source bundle ID does not exist',
        updater.Update, [('factory_toolkit', FACTORY_TOOLKIT_DIR)],
        source_id='not_exist')

    self.assertRaisesRegexp(
        common.UmpireError, 'Destination bundle ID already exists',
        updater.Update, [('factory_toolkit', FACTORY_TOOLKIT_DIR)],
        dest_id='default_test')

  def testUpdateInvalidInput(self):
    updater = update.ResourceUpdater(self.env)
    self.assertRaisesRegexp(
        common.UmpireError, 'Unsupported resource type', updater.Update,
        [('unsupported', FACTORY_TOOLKIT_DIR)])

    self.assertRaisesRegexp(
        common.UmpireError, 'Resource not found', updater.Update,
        [('factory_toolkit', os.path.join(self.env.base_dir, 'not_exist'))])

  def testAllUpdatableResource(self):
    BIOS_VERSION = 'bios_0.0.1'
    EC_VERSION = 'ec_0.0.2'
    PD_VERSION = 'pd_0.0.3'
    FSI_VERSION = '0.0.1'

    firmware_path = os.path.join(self.env.base_dir, 'firmware.gz')
    file_utils.WriteFile(firmware_path, 'new firmware')
    new_firmware_resource = 'firmware.gz#%s:%s:%s#f56ca36e' % (
        BIOS_VERSION, EC_VERSION, PD_VERSION)

    fsi_path = os.path.join(self.env.base_dir, 'rootfs-release.gz')
    file_utils.WriteFile(fsi_path, 'new fsi')
    new_fsi_resource = 'rootfs-release.gz#%s#932ecf09' % FSI_VERSION

    # HWID version extracted from hwid.gz's checksum field.
    hwid_path = os.path.join(TESTDATA_DIR, 'hwid.gz')
    new_hwid_resource = ('hwid.gz#a95cd8def470df2e7a8d549af887897e2d095bb0'
                         '#061d5528')

    # TODO(deanliao): use real firmware.gz/rootfs-release.gz in which
    #     Umpire can extract version from.
    mox_obj = mox.Mox()
    mox_obj.StubOutWithMock(
        get_version, 'GetFirmwareVersionsFromOmahaChannelFile')
    mox_obj.StubOutWithMock(
        get_version, 'GetReleaseVersionFromOmahaChannelFile')

    get_version.GetFirmwareVersionsFromOmahaChannelFile(
        firmware_path).AndReturn((BIOS_VERSION, EC_VERSION, PD_VERSION))
    get_version.GetReleaseVersionFromOmahaChannelFile(
        fsi_path, no_root=True).AndReturn(FSI_VERSION)

    mox_obj.ReplayAll()
    updater = update.ResourceUpdater(self.env)
    updated_config_path = updater.Update([
        ('factory_toolkit', FACTORY_TOOLKIT_DIR),
        ('firmware', firmware_path),
        ('fsi', fsi_path),
        ('hwid', hwid_path)])
    updated_bundle = config.UmpireConfig(updated_config_path).GetDefaultBundle()

    self.assertEqual('default_test', updated_bundle['id'])
    resources = updated_bundle['resources']
    self.assertEqual(FACTORY_TOOLKIT_RES,
                     resources['device_factory_toolkit'])
    self.assertEqual(new_firmware_resource, resources['firmware'])
    self.assertEqual(new_fsi_resource, resources['rootfs_release'])
    self.assertEqual(new_hwid_resource, resources['hwid'])

    mox_obj.UnsetStubs()
    mox_obj.VerifyAll()

  # TODO(littlecvr): remove this once mini-omaha changed its protocol.
  def testUpdateFSIFromChromeOSImage(self):
    MOCK_FSI_PARTITIONS = [
        {'num': 1, 'label': 'STATE', 'type': 'data', 'sectors': 128},
        {'num': 2, 'label': 'KERN-A', 'type': 'kernel', 'sectors': 16},
        {'num': 3, 'label': 'ROOT-A', 'type': 'rootfs', 'sectors': 32},
        {'num': 4, 'label': 'KERN-B', 'type': 'kernel', 'sectors': 16},
        {'num': 5, 'label': 'ROOT-B', 'type': 'rootfs', 'sectors': 32}]
    # CGPT structure (before creating any partitions):
    #   [content]       [start]     [sectors]
    #   PMBR            0           1
    #   pri header      1           1
    #   pri table       2           32
    #   (empty)         34          ${TOTAL}-1-1-32-32-1
    #   sec table       ${END}-33   32
    #   sec header      $(END}-1    1
    MOCK_FSI_IMAGE_SIZE = update.SECTOR_SIZE * (
        1 + 1 + 32 + 32 + 1 +  # PMBR + CPGT headers
        sum(p['sectors'] for p in MOCK_FSI_PARTITIONS))
    CGPT_HEADER_SECTORS = 1 + 1 + 32

    # mk_memento_images.sh is in setup
    MK_MEMENTO_IMAGES_SH_PATH = os.path.realpath(TEST_DIR)
    MK_MEMENTO_IMAGES_SH_PATH = os.path.join(
        MK_MEMENTO_IMAGES_SH_PATH,
        '..', '..', '..', 'setup', 'mk_memento_images.sh')

    with file_utils.TempDirectory() as temp_dir:
      # Create a fake FSI image.
      input_path = os.path.join(temp_dir, 'input.bin')
      with open(input_path, 'wb') as fin:
        fin.write(os.urandom(MOCK_FSI_IMAGE_SIZE))

      # cgpt will complain that the header's broken but that's fine
      subprocess.check_call(['cgpt', 'create', input_path])

      current_partition_start = CGPT_HEADER_SECTORS
      for partition in MOCK_FSI_PARTITIONS:
        subprocess.check_call([
            'cgpt', 'add', '-i', str(partition['num']),
            '-b', str(current_partition_start),
            '-s', str(partition['sectors']),
            '-t', partition['type'],
            '-l', partition['label'],
            input_path])
        current_partition_start += partition['sectors']

      output_memento_path = os.path.join(temp_dir, 'memento.gz')
      subprocess.check_call([
          MK_MEMENTO_IMAGES_SH_PATH,
          '%s:%d' % (input_path, update.MINI_OMAHA_KERNEL_PART_NUM),
          '%s:%d' % (input_path, update.MINI_OMAHA_ROOTFS_PART_NUM),
          output_memento_path])

      # Call ConvertChromeOSImageToMiniOmahaFormat() to generate the output.
      output_path = os.path.join(temp_dir, update.MINI_OMAHA_FSI_EXPECTED_NAME)
      update.ConvertChromeOSImageToMiniOmahaFormat(input_path, output_path)

      # Compare the ground truth and the output.
      with gzip.open(output_path) as fa:
        with gzip.open(output_memento_path) as fb:
          self.assertEqual(
              fa.read(), fb.read(),
              msg='Outputs of mk_momento_images.sh and '
                  'update.ConvertChromeOSImageToMiniOmahaFormat are different')


if __name__ == '__main__':
  unittest.main()
