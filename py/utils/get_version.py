#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to get release image and firmware version."""

import logging
import os
import re

import factory_common  # pylint: disable=W0611
from cros.factory.tools.mount_partition import MountPartition
from cros.factory.utils.file_utils import GunzipSingleFile, SetFileExecutable
from cros.factory.utils.process_utils import Spawn


def GetReleaseVersion(mount_point):
  """Gets CHROMEOS_RELEASE_VERSION of the rootfs partition.

  Args:
    mount_point: partition mount point.

  Returns:
    Release version (in mount_point/etc/lsb-release);
    None if not found.
  """
  lsb_release = os.path.join(mount_point, 'etc', 'lsb-release')
  if not os.path.isfile(lsb_release):
    return None
  match = re.search('^CHROMEOS_RELEASE_VERSION=(.+)$',
                    open(lsb_release).read(), re.MULTILINE)
  if not match:
    return None
  return match.group(1)


def GetFirmwareVersions(updater):
  """Gets the firmware versions in firmware updater.

  Args:
    updater: Path to a firmware updater.

  Returns:
    (bios_version, ec_version). If no firmware/EC version is found,
    sets version to None.
  """
  try:
    command = [updater, '-V']
    stdout = Spawn(command, log=True, check_output=True).stdout_data
  except Exception as e:
    logging.error('Unable to run "%s", reason: %s', ' '.join(command), e)
    return (None, None)

  versions = []
  for label in ['BIOS', 'EC']:
    match = re.search('^' + label + ' version:\s+(.+)$', stdout, re.MULTILINE)
    versions.append(match.group(1) if match else None)
  return tuple(versions)


def GetFirmwareVersionsFromOmahaChannelFile(path):
  """Gets firmware versions from Omaha channel file.

  Omaha channel file (gzipped) is often in
  <bundle_dir>/factory_setup/static/firmware.gz

  Args:
    path: Channel file path.

  Returns:
    (bios_version, ec_version). If no firmware/EC version is found,
    sets version to None.
  """
  with GunzipSingleFile(path) as unzip_path:
    SetFileExecutable(unzip_path)
    return GetFirmwareVersions(unzip_path)


def GetReleaseVersionFromOmahaChannelFile(path):
  """Gets release image version from Omaha channel file.

  Omaha channel file (gzipped) is often in
  <bundle_dir>/factory_setup/static/rootfs-test.gz
  <bundle_dir>/factory_setup/static/rootfs-release.gz

  Args:
    path: Channel file path.

  Returns:
    Release version (in mount_point/etc/lsb-release);
    None if not found.
  """
  with GunzipSingleFile(path) as unzip_path:
    with MountPartition(unzip_path, is_omaha_channel=True) as mount_point:
      return GetReleaseVersion(mount_point)
