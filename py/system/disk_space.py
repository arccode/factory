#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import collections
import os


# Stub for mockability.
_Open = open


VFSInfo = collections.namedtuple('VFSInfo', ['mount_points', 'statvfs'])
def GetAllVFSInfo():
  '''Returns results for statvfs on all filesystems.

  The returned value is a map from device to VFSInfo object.  VFSInfo
  is a named tuple with fields:

     mount_points: List of all mount points for the device.
     statvfs: Result of calling os.statvfs on the device.
  '''
  # Path from each device to the paths it is mounted at
  device_to_path = collections.defaultdict(lambda: [])

  for line in _Open('/etc/mtab'):
    device, path, fs_type = line.split()[0:3]
    if fs_type in [
        'sysfs', 'proc', 'fusectl', 'debugfs', 'rootfs', 'pstore', 'devpts']:
      continue
    device_to_path[device].append(path)

  ret = {}
  for k, v in sorted(device_to_path.items()):
    try:
      ret[k] = VFSInfo(sorted(v), os.statvfs(v[0]))
    except OSError:
      # Oh well; skip this guy
      pass

  return ret


def FormatSpaceUsed(vfs_info):
  '''Formats disk space used for a single filesystem.

  Returns:
    A string like

      [/a /b: 87%/17%]

    meaning that on the device that /a and /b are mounted from, 87% of bytes
    and 17% of inodes are used (unavailable to unprivileged users).
  '''
  return '%s: %d%%/%d%%' % (
      ' '.join(vfs_info.mount_points),
      (100 -
       100.0 * vfs_info.statvfs.f_bavail / (vfs_info.statvfs.f_blocks or 1)),
      (100 -
       100.0 * vfs_info.statvfs.f_favail / (vfs_info.statvfs.f_files or 1)))


def FormatSpaceUsedAll():
  '''Formats disk space used by all filesystems.

  The list is arranged in descending order of space used.

  Returns:
    A string like

      Space used (bytes%/inode%): [/a /b: 87%/17%] [/c: 5%/3%]
  '''
  vfs_infos = GetAllVFSInfo()
  return 'Disk space used (bytes%/inodes%): ' + ' '.join(
      '[' + FormatSpaceUsed(v) + ']'
      for v in sorted(
          vfs_infos.values(),
          key=lambda x: float(x.statvfs.f_bavail) / (x.statvfs.f_blocks or 1)))


if __name__ == '__main__':
  print FormatSpaceUsedAll()
