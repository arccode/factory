# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import codecs
import glob
import logging
import os
import re
import string  # pylint: disable=deprecated-module
import struct

from cros.factory.probe.functions import file as file_module
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


STORAGE_SYSFS_PATH = '/sys/class/block/*'
SMARTCTL_PATH = '/usr/sbin/smartctl'


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

def CookVersion(raw_version):
  """Returns human readable version string."""
  version = ''.join('%02x' % c for c in raw_version)
  # The output for firmware version is encoded by hexdump of a ASCII
  # string or hexdump of hexadecimal values, always in 8 characters.
  # For example, version 'ABCDEFGH' is:
  # [raw_version[7]]: 0x48
  # [raw_version[6]]: 0x47
  # [raw_version[5]]: 0x46
  # [raw_version[4]]: 0x45
  # [raw_version[3]]: 0x44
  # [raw_version[2]]: 0x43
  # [raw_version[1]]: 0x42
  # [raw_version[0]]: 0x41
  #
  # Some vendors might use hexadecimal values for it.
  # For example, version 3 is:
  # [raw_version[7]]: 0x00
  # [raw_version[6]]: 0x00
  # [raw_version[5]]: 0x00
  # [raw_version[4]]: 0x00
  # [raw_version[3]]: 0x00
  # [raw_version[2]]: 0x00
  # [raw_version[1]]: 0x00
  # [raw_version[0]]: 0x03
  #
  # To handle both cases, this function returns a 64-bit hexadecimal value
  # and will try to decode it as a ASCII string or as a 64-bit little-endian
  # integer. It returns '4142434445464748 (ABCDEFGH)' for the first example
  # and returns '0300000000000000 (3)' for the second example.

  # Try to decode it as a ASCII string.
  # Note vendor may choose SPACE (0x20), NEWLINE (0x0a) or NUL (0x00) to pad
  # version string, so we want to strip both in the human readable part.
  ascii_string = ''.join(map(chr, raw_version)).strip(' \0\n')
  if ascii_string and all(
      (c in string.ascii_letters or c in string.digits) for c in ascii_string):
    version += ' (%s)' % ascii_string
  else:
    # Try to decode it as a 64-bit little-endian integer.
    version += ' (%s)' % struct.unpack_from('<q', codecs.decode(version,
                                                                'hex'))
  return version

def GetStorageFirmwareVersion(node_path):
  """Extracts firmware version.

  Args:
    node_path: the node_path returned by GetFixedDevices(). For example,
        '/sys/class/block/mmcblk0'.

  Returns:
    A string indicating the firmware version if firmware version is found.
    Return None if firmware version doesn't present.
  """
  dev_path = os.path.join(node_path, 'device')
  # Use fwrev file (e.g., for eMMC)
  emmc_fw_vr = file_module.ReadFile(os.path.join(dev_path, 'fwrev'))
  if emmc_fw_vr:
    # Cast a hex string to a 64-bit little-endian integer and then decode it to
    # a list of 8 bytes.
    # For exmaple, if emmc_fw_vr = '0x4142434445464748' then raw_version =
    # [0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48]
    raw_version = [((int(emmc_fw_vr, 0) >> ((7-i)*8)) & 255) for i in range(8)]
    return CookVersion(raw_version)
  # Use firmware_rev file (e.g., for NVMe)
  # It is possible that the 8th byte is a space, and it will be stripped off if
  # binary_mode is false.
  nvme_fw_vr = file_module.ReadFile(os.path.join(dev_path, 'firmware_rev'),
                                    binary_mode=True)
  if nvme_fw_vr:
    raw_version = [int(x, 0) for x in nvme_fw_vr.split(' ')[0:8]]
    # Some firmware versions are less than 8 bytes.
    if len(raw_version) < 8:
      raw_version.extend([0] * (8 - len(raw_version)))
    return CookVersion(raw_version)
  # Use smartctl (e.g., for SATA)
  sata_dev_path = os.path.join('/dev', os.path.basename(node_path))
  smartctl = process_utils.SpawnOutput([SMARTCTL_PATH, '--all', sata_dev_path],
                                       log=True)
  matches = re.findall(r'(?m)^Firmware Version:\s+(.+)$', smartctl)
  if matches:
    cooked_version = matches[-1]
    if re.search(r'(?m)^Device Model:\s+SanDisk', smartctl):
      # Canonicalize SanDisk firmware versions by replacing 'CS' with '11'.
      # According to b/35513546, 'CS's in firmware version of SanDisk are
      # equivalent to '11's.
      cooked_version = re.sub('^CS', '11', cooked_version)
    return CookVersion(list(map(ord, cooked_version)))
  return None

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
    fw_version = GetStorageFirmwareVersion(node_path)
    if fw_version is not None:
      data['fw_version'] = fw_version
    size_path = os.path.join(os.path.dirname(dev_path), 'size')
    data['sectors'] = (file_utils.ReadFile(size_path).strip()
                       if os.path.exists(size_path) else '')
    return data
