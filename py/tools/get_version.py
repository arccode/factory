# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to get release image and firmware version."""

from __future__ import print_function

import logging
import os
import re
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.sys_utils import MountPartition


FIRMWARE_LABELS = ('BIOS', 'EC', 'PD')
EMPTY_FIRMWARE_TUPLE = tuple([None] * len(FIRMWARE_LABELS))


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
  """Gets the firmware versions in firmware updater. Supports gzipped file.

  Omaha channel file (gzipped) is often in
  <bundle_dir>/setup/static/firmware.gz

  Args:
    updater: Path to a firmware updater.

  Returns:
    (bios_version, ec_version, pd_version). If no firmware/EC/PD version is
    found, sets version to None.
  """
  def _GetFirmwareVersions(updater):
    try:
      command = ['sh', updater, '-V']
      stdout = process_utils.CheckOutput(command, log=True)
    except Exception as e:
      logging.error('Unable to run "%s", reason: %s', ' '.join(command), e)
      return EMPTY_FIRMWARE_TUPLE

    versions = []
    for label in FIRMWARE_LABELS:
      match = re.search('^' + label + r' version:\s*(.+)$', stdout,
                        re.MULTILINE)
      versions.append(match.group(1) if match else None)
    return tuple(versions)

  if file_utils.IsGzippedFile(updater):
    with file_utils.GunzipSingleFile(updater) as unzip_path:
      return _GetFirmwareVersions(unzip_path)
  else:
    return _GetFirmwareVersions(updater)


def GetFirmwareVersionsWithLabel(updater):
  """Gets the firmware versions in firmware updater.

  Args:
    updater: Path to a firmware updater.

  Returns:
    {'BIOS': bios_version, 'EC': ec_version, 'PD': pd_version}.
    If the firmware is not found, the version will be None.
  """
  return dict(zip(FIRMWARE_LABELS, GetFirmwareVersions(updater)))


def GetFirmwareBinaryVersion(path):
  """Gets the version stored in RO_FRID section of the firmware binary.

  Note that this function relies on dump_fmap, which is only available on a CrOS
  device or inside CrOS SDK chroot.

  Args:
    path: Path to the firmware binary.

  Returns:
    The extracted firmware version as a string; or None if the function fails to
    extract version.
  """
  binary_path = os.path.abspath(path)
  result = None
  try:
    with file_utils.TempDirectory(prefix='dump_fmap') as temp_dir:
      process_utils.Spawn(['dump_fmap', '-x', binary_path], ignore_stdout=True,
                          log=True, cwd=temp_dir, check_call=True)
      with open(os.path.join(temp_dir, 'RO_FRID')) as f:
        result = f.read().strip('\x00')   # Strip paddings.
  except (subprocess.CalledProcessError, IOError):
    logging.exception(
        'Failed to extract firmware version from %s.', binary_path)
  return result


def GetReleaseVersionFromOmahaChannelFile(path, no_root=False):
  """Gets release image version from Omaha channel file.

  Omaha channel file (gzipped) is often in
  <bundle_dir>/setup/static/rootfs-test.gz
  <bundle_dir>/setup/static/rootfs-release.gz

  Args:
    path: Channel file path.
    noroot: Flag to indicate no root access.

  Returns:
    Release version (in mount_point/etc/lsb-release);
    None if not found.
  """
  if no_root:
    # zcat channel.gz | strings | grep CHROMEOS_RELEASE_VERSION=
    zcat_process = subprocess.Popen(('zcat', path), stdout=subprocess.PIPE)
    strings_process = subprocess.Popen(('strings'), stdin=zcat_process.stdout,
                                       stdout=subprocess.PIPE)
    grep_output = subprocess.check_output(('grep', 'CHROMEOS_RELEASE_VERSION='),
                                          stdin=strings_process.stdout)
    zcat_process.stdout.close()
    strings_process.stdout.close()
    strings_process.wait()
    zcat_process.wait()
    match = re.search('^CHROMEOS_RELEASE_VERSION=(.+)$', grep_output,
                      re.MULTILINE)
    if not match:
      return None
    return match.group(1)

  with file_utils.GunzipSingleFile(path) as unzip_path:
    with MountPartition(unzip_path, is_omaha_channel=True) as mount_point:
      return GetReleaseVersion(mount_point)


def GetHWIDVersion(path):
  """Gets HWID version from HWID v3 bundle file.

  It also verifies checksum.

  Args:
    path: HWID v3 bundle file path ('.gz' supported).

  Returns:
    HWID checksum as version. None if file is not found or checksum failed.
  """
  if file_utils.IsGzippedFile(path):
    with file_utils.GunzipSingleFile(path) as unzip_path:
      return GetHWIDVersion(unzip_path)
  if file_utils.ReadFile(path).startswith('#!/bin/sh\n'):
    with file_utils.TempDirectory() as tmp_dir:
      process_utils.Spawn(['sh', path, tmp_dir], log=True, check_call=True,
                          ignore_stdout=True)
      process_utils.Spawn('mv -f * hwid', cwd=tmp_dir, log=True, shell=True,
                          check_call=True)
      return GetHWIDVersion(os.path.join(tmp_dir, 'hwid'))
  hwid = file_utils.ReadFile(path)
  match = re.search(r'^checksum: (.*)$', hwid, flags=re.MULTILINE)
  if not match:
    logging.warning('Cannot extract checksum from HWID: %s', path)
    return None
  expected_checksum = match.group(1)
  actual_checksum = hwid_utils.ComputeDatabaseChecksum(path)
  if expected_checksum != actual_checksum:
    logging.warning('HWID verification failed: expected: %s actual: %s',
                    expected_checksum, actual_checksum)
    return None
  return expected_checksum
