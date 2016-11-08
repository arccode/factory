# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Updates a resource in a bundle.

See ResourceUpdater for detail.
"""

import copy
import gzip
import os
import re
import shutil
import struct
import subprocess
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire import utils
from cros.factory.utils import file_utils


# Mapping of updateable resource type (command string) to ResourceType enum.
_RESOURCE_TYPE_MAP = {
    'factory_toolkit': common.ResourceType.FACTORY_TOOLKIT,
    'firmware': common.ResourceType.FIRMWARE,
    'fsi': common.ResourceType.ROOTFS_RELEASE,
    'hwid': common.ResourceType.HWID}

# TODO(crosbug.com/p/51534): remove this once mini-omaha changed its protocol.
SECTOR_SIZE = 512
MINI_OMAHA_FSI_EXPECTED_NAME = 'rootfs-release.gz'
MINI_OMAHA_KERNEL_PART_NUM = 4
MINI_OMAHA_ROOTFS_PART_NUM = 5


# TODO(crosbug.com/p/51534): remove this once mini-omaha changed its protocol.
def IsChromeOSImage(resource_basename):
  # chromeos_${version}_${board}_recovery_${channel}_${key}.bin
  if re.match(r'chromeos_[^_]*_[^_]*_recovery_[^-]*-channel_[^.]*.bin',
              resource_basename):
    return True
  return False


# TODO(crosbug.com/p/51534): remove this once mini-omaha changed its protocol.
def ConvertChromeOSImageToMiniOmahaFormat(chromeos_image_path,
                                          output_path=None):
  """Converts image from CPFE or GoldenEye to mini-omaha format.

  An image from CPFE or GoldenEye is a complete image that contains stateful
  partition, kernel-a, rootfs-a, kernel-b, rootfs-b, EFI, etc. But due to
  historical reason, mini-omaha needs a different format. To make the user
  able to import an image from CPFE or GoldenEye directly, we need to convert
  it.

  Specifically, this is what mk_memento_images.sh does.

  If output_path is None, this function creates a temp folder and converts the
  input image to a file called "rootfs-release.gz" under that temp folder. The
  path to the "rootfs-release.gz" is returned, and can be used by mini-omaha
  directly. Note that in this case, it's the caller's reponsibility to remove
  the temp folder.

  If output_path is not None, the content will be written to it. The
  output_path must ends with "rootfs-release.gz", or ValueError will be raised.
  """
  def Sectors2Size(sectors):
    return SECTOR_SIZE * sectors

  def GetPartitionOffset(partition_number, image_path):
    return Sectors2Size(int(subprocess.check_output([
        'cgpt', 'show', '-i', str(partition_number), '-b', image_path])))

  def GetPartitionSize(partition_number, image_path):
    return Sectors2Size(int(subprocess.check_output([
        'cgpt', 'show', '-i', str(partition_number), '-s', image_path])))

  kernel_size = GetPartitionSize(
      MINI_OMAHA_KERNEL_PART_NUM, chromeos_image_path)
  kernel_offset = GetPartitionOffset(
      MINI_OMAHA_KERNEL_PART_NUM, chromeos_image_path)
  rootfs_size = GetPartitionSize(
      MINI_OMAHA_ROOTFS_PART_NUM, chromeos_image_path)
  rootfs_offset = GetPartitionOffset(
      MINI_OMAHA_ROOTFS_PART_NUM, chromeos_image_path)

  if output_path is None:
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, MINI_OMAHA_FSI_EXPECTED_NAME)
  else:
    if os.path.basename(output_path) != MINI_OMAHA_FSI_EXPECTED_NAME:
      raise ValueError(
          'basename of output_path must be %s' % MINI_OMAHA_FSI_EXPECTED_NAME)

  # Write signature, kernal, rootfs to "rootfs-release.gz" in the temp folder.
  with gzip.open(output_path, 'wb', compresslevel=9) as fout:
    # signature
    fout.write(struct.pack('>q', kernel_size))
    # kernel and rootfs
    with open(chromeos_image_path) as fin:
      fin.seek(kernel_offset)
      fout.write(fin.read(kernel_size))
      fin.seek(rootfs_offset)
      fout.write(fin.read(rootfs_size))

  return output_path


class ResourceUpdater(object):
  """Updates a resource in a bundle from active config.

  It copies the given resources to Umpire repository. Then updates the
  specified bundle's resource mapping. Finally, it adds the updated config
  to resources and marks it as staging.

  Usage:
    resource_updater = ResourceUpdater(env)
    ResourceUpdater.Update(resources_to_update, source_id='old_bundle_id',
                           dest_id='new_bundle_id')
  """

  def __init__(self, env):
    """Constructor.

    It copies active config (env.config) to be modified.
    It checks env.HasStagingConfigFile(). If True, raises exception.

    Args:
      env: UmpireEnv object.

    Raises:
      common.UmpireError if staging config exists.
    """
    if env.HasStagingConfigFile():
      raise common.UmpireError(
          'Cannot update resources as staging config exists. '
          'Please run "umpire unstage" to unstage or "umpire deploy" to '
          'deploy the staging config first.')

    self._env = env

    # Copy current config for editing.
    self._config = umpire_config.UmpireConfig(env.config)

    self._config_basename = os.path.basename(env.config_path)
    self._target_bundle = None

  def Update(self, resources_to_update, source_id=None, dest_id=None):
    """Updates resource(s) in a bundle.

    Args:
      resources_to_update: list of (resource_type, resource_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.

    Returns:
      Path to updated config file in resources.
    """
    if not source_id:
      source_id = self._config.GetDefaultBundle()['id']

    self._SanityCheck(resources_to_update)
    self._PrepareTargetBundle(source_id, dest_id)
    self._UpdateResourceMap(resources_to_update)
    return self._WriteToStagingConfig()

  def _PrepareTargetBundle(self, source_id, dest_id):
    target_bundle = self._config.GetBundle(source_id)
    if not target_bundle:
      raise common.UmpireError(
          'Source bundle ID does not exist: %s' % source_id)

    if dest_id:
      if self._config.GetBundle(dest_id):
        raise common.UmpireError(
            'Destination bundle ID already exists: %s' % dest_id)
      target_bundle = copy.deepcopy(target_bundle)
      target_bundle['id'] = dest_id
      self._config['bundles'].insert(0, target_bundle)

    self._target_bundle = target_bundle

  def _SanityCheck(self, resources):
    for resource_type, resource_path in resources:
      if resource_type not in common.UPDATEABLE_RESOURCES:
        raise common.UmpireError(
            'Unsupported resource type: %s' % resource_type)
      if not os.path.isfile(resource_path):
        raise common.UmpireError('Resource not found: %s' % resource_path)

  def _UpdateResourceMap(self, resources):
    resource_map = self._target_bundle['resources']
    for resource_type, resource_path in resources:
      # TODO(crosbug.com/p/51534): remove this once mini-omaha changed its
      #                            protocol.
      basename = os.path.basename(resource_path)
      if IsChromeOSImage(basename):
        converted_resource_path = ConvertChromeOSImageToMiniOmahaFormat(
            resource_path)
      else:
        converted_resource_path = resource_path

      try:
        resource_name = os.path.basename(
            self._env.AddResource(
                converted_resource_path,
                res_type=_RESOURCE_TYPE_MAP.get(resource_type)))

      finally:
        if IsChromeOSImage(basename):
          temp_dir = os.path.dirname(converted_resource_path)
          try:
            shutil.rmtree(temp_dir)
          except:  # pylint: disable=W0702
            raise common.UmpireError('Cannot remove temp folder %s' % temp_dir)

      if resource_type == 'factory_toolkit':
        resource_map['device_factory_toolkit'] = resource_name
        utils.UnpackFactoryToolkit(self._env, resource_name)

      elif resource_type == 'fsi':
        resource_map['rootfs_release'] = resource_name
      else:
        resource_map[resource_type] = resource_name

  def _WriteToStagingConfig(self):
    """Writes self._config to resources and set it as staging.

    Returns:
      config path in resources.
    """
    with file_utils.TempDirectory() as temp_dir:
      temp_config_path = os.path.join(temp_dir, self._config_basename)
      self._config.WriteFile(temp_config_path)
      res_path = self._env.AddResource(temp_config_path)
      self._env.StageConfigFile(res_path)
      return res_path
