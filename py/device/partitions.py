# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Partitions on ChromeOS devices."""

from cros.factory.device import device_types


class DiskPartition:
  """Information of a partition on a Linux device.

  Properties:
    name: A human-readable reference name of the partition.
    index: Numeric index of the partition.
    disk: A string of path to the disk holding the partition.
    path: A string for complete path to access this partition.
  """

  def __init__(self, disk, name, index):
    self.disk = disk
    self.name = name
    self.index = index
    if disk and disk[-1].isdigit():
      self.path = disk + 'p' + str(self.index)
    else:
      self.path = disk + str(self.index)


class Partitions(device_types.DeviceComponent):
  """Partitions of system boot disk."""

  @device_types.DeviceProperty
  def rootdev(self):
    """Gets root block device."""
    # rootdev may return /dev/dm-\d+ when LVM is enabled.  'rootdev -s -d' can
    # return simple format like /dev/sd[a-z] or /dev/mmcblk\d+.
    return self._device.CheckOutput(['rootdev', '-s', '-d']).strip()

  @device_types.DeviceProperty
  def STATEFUL(self):
    return DiskPartition(self.rootdev, 'STATEFUL', 1)

  @device_types.DeviceProperty
  def FACTORY_KERNEL(self):
    return DiskPartition(self.rootdev, 'FACTORY_KERNEL', 2)

  @device_types.DeviceProperty
  def FACTORY_ROOTFS(self):
    return DiskPartition(self.rootdev, 'FACTORY_ROOTFS', 3)

  @device_types.DeviceProperty
  def RELEASE_KERNEL(self):
    return DiskPartition(self.rootdev, 'RELEASE_KERNEL', 4)

  @device_types.DeviceProperty
  def RELEASE_ROOTFS(self):
    return DiskPartition(self.rootdev, 'RELEASE_ROOTFS', 5)

  @device_types.DeviceProperty
  def MINIOS_A(self):
    return DiskPartition(self.rootdev, 'MINIOS_A', 9)

  @device_types.DeviceProperty
  def MINIOS_B(self):
    return DiskPartition(self.rootdev, 'MINIOS_B', 10)
