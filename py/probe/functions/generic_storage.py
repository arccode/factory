# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os
import re
import string  # pylint: disable=deprecated-module
import struct

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


STORAGE_SYSFS_PATH = '/sys/class/block/*'


def GetFixedDevices():
  """Returns paths to all fixed storage devices on the system."""
  ret = []
  for node in sorted(glob.glob(STORAGE_SYSFS_PATH)):
    path = os.path.join(node, 'removable')
    if not os.path.exists(path) or file_utils.ReadFile(path).strip() != '0':
      continue
    if re.match(r'^loop|^dm-', os.path.basename(node)):
      # Loopback or dm-verity device; skip
      continue
    ret.append(node)
  return ret


def GetEMMC5FirmwareVersion(node_path):
  """Extracts eMMC 5.0 firmware version from EXT_CSD[254:261].

  Args:
    node_path: the node_path returned by GetFixedDevices(). For example,
        '/sys/class/block/mmcblk0'.

  Returns:
    A string indicating the firmware version if firmware version is found.
    Return None if firmware version doesn't present.
  """
  ext_csd = process_utils.GetLines(process_utils.SpawnOutput(
      'mmc extcsd read /dev/%s' % os.path.basename(node_path),
      shell=True, log=True))
  # The output for firmware version is encoded by hexdump of a ASCII
  # string or hexdump of hexadecimal values, always in 8 characters.
  # For example, version 'ABCDEFGH' is:
  # [FIRMWARE_VERSION[261]]: 0x48
  # [FIRMWARE_VERSION[260]]: 0x47
  # [FIRMWARE_VERSION[259]]: 0x46
  # [FIRMWARE_VERSION[258]]: 0x45
  # [FIRMWARE_VERSION[257]]: 0x44
  # [FIRMWARE_VERSION[256]]: 0x43
  # [FIRMWARE_VERSION[255]]: 0x42
  # [FIRMWARE_VERSION[254]]: 0x41
  #
  # Some vendors might use hexadecimal values for it.
  # For example, version 3 is:
  # [FIRMWARE_VERSION[261]]: 0x00
  # [FIRMWARE_VERSION[260]]: 0x00
  # [FIRMWARE_VERSION[259]]: 0x00
  # [FIRMWARE_VERSION[258]]: 0x00
  # [FIRMWARE_VERSION[257]]: 0x00
  # [FIRMWARE_VERSION[256]]: 0x00
  # [FIRMWARE_VERSION[255]]: 0x00
  # [FIRMWARE_VERSION[254]]: 0x03
  #
  # To handle both cases, this function returns a 64-bit hexadecimal value
  # and will try to decode it as a ASCII string or as a 64-bit little-endian
  # integer. It returns '4142434445464748 (ABCDEFGH)' for the first example
  # and returns '0300000000000000 (3)' for the second example.

  pattern = re.compile(r'^\[FIRMWARE_VERSION\[(\d+)\]\]: (.*)$')
  data = dict(m.groups() for m in map(pattern.match, ext_csd) if m)
  if not data:
    return None

  raw_version = [int(data[str(i)], 0) for i in range(254, 262)]
  version = ''.join(('%02x' % c for c in raw_version))

  # Try to decode it as a ASCII string.
  # Note vendor may choose SPACE (0x20) or NUL (0x00) to pad version string,
  # so we want to strip both in the human readable part.
  ascii = ''.join(map(chr, raw_version)).strip(' \0')
  if ascii and all(c in string.printable for c in ascii):
    version += ' (%s)' % ascii
  else:
    # Try to decode it as a 64-bit little-endian integer.
    version += ' (%s)' % struct.unpack_from('<q', version.decode('hex'))
  return version


class GenericStorageFunction(cached_probe_function.CachedProbeFunction):
  """Probe the generic storage information."""
  ATA_FIELDS = ['vendor', 'model']
  EMMC_FIELDS = ['type', 'name', 'hwrev', 'oemid', 'manfid']
  NVME_FIELDS = ['vendor', 'device', 'class']
  # Another field 'cid' is a combination of all other fields so we should not
  # include it again.
  EMMC_OPTIONAL_FIELDS = ['prv']

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    return [ident for ident in map(cls._ProcessNode, GetFixedDevices())
            if ident is not None]

  @classmethod
  def _ProcessNode(cls, node_path):
    logging.info('Processing the node: %s', node_path)
    dev_path = os.path.join(node_path, 'device')
    # The directory layout for NVMe is "/<path>/device/device/<entries>"
    nvme_dev_path = os.path.join(dev_path, 'device')
    data = (sysfs.ReadSysfs(dev_path, cls.ATA_FIELDS) or
            sysfs.ReadSysfs(nvme_dev_path, cls.NVME_FIELDS) or
            sysfs.ReadSysfs(dev_path, cls.EMMC_FIELDS,
                            cls.EMMC_OPTIONAL_FIELDS))
    if not data:
      return None
    emmc5_fw_ver = GetEMMC5FirmwareVersion(node_path)
    if emmc5_fw_ver is not None:
      data['emmc5_fw_ver'] = emmc5_fw_ver
    size_path = os.path.join(os.path.dirname(dev_path), 'size')
    data['sectors'] = (file_utils.ReadFile(size_path).strip()
                       if os.path.exists(size_path) else '')
    return data
