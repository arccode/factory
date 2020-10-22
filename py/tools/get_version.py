#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to get release image and firmware version."""

import argparse
import logging
import os
import re

from cros.factory.hwid.v3 import hwid_utils
from cros.factory.utils import file_utils
from cros.factory.utils import fmap
from cros.factory.utils import process_utils


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

  Args:
    path: Path to the firmware binary.

  Returns:
    The extracted firmware version as a string; or None if the function fails to
    extract version.
  """
  result = None
  try:
    return fmap.FirmwareImage(
        file_utils.ReadFile(path, encoding=None)).get_section(
            'RO_FRID').strip(b'\xff').strip(b'\x00').decode('utf-8')
  except Exception:
    logging.exception(
        'Failed to extract firmware version from: %s', path)
  return result


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


def GetBoardVersion():
  """Gets board version.

  The purpose of this function is to replace `mosys platform version`.

  Get board version from the following orders:
  1. File: /proc/device-tree/firmware/coreboot/board-id (For ARM FDT board)
     Note: This is a big-endian 32-bit integer (4 bytes).
  2. File: /sys/class/dmi/id/product_version (For x86 SMBIOS board)
  3. Command: `ectool boardversion` (Fall back purpose)

  Returns:
    Board version, empty string if all methods fail.
    e.g. 'rev0', ''.
  """
  board_id_path = '/proc/device-tree/firmware/coreboot/board-id'
  if os.path.exists(board_id_path):
    with open(board_id_path, 'rb') as f:
      return 'rev' + str(int.from_bytes(f.read(), 'big'))

  commands = [['cat', '/sys/class/dmi/id/product_version'],
              ['ectool', 'boardversion']]

  for cmd in commands:
    version = process_utils.SpawnOutput(cmd, ignore_stderr=True).strip(' \0\n')
    if version:
      if version.isnumeric():
        version = 'rev' + version

      return version

  return ''


def main():
  logging.basicConfig(level=logging.INFO)

  parser = argparse.ArgumentParser(
      description=('Get version from artifact we used.'),
      formatter_class=argparse.RawDescriptionHelpFormatter)
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument('--board', action='store_true', help='Get board version.')
  args = parser.parse_args()

  if args.board:
    print(GetBoardVersion())


if __name__ == '__main__':
  main()
