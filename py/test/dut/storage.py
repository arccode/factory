#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing access to permanet storage on DUT"""

import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


class Storage(component.DUTComponent):
  """Persistent storage on DUT."""

  def GetFactoryRoot(self):
    """Returns the directory for factory environment (code and resources)."""
    return '/usr/local/factory'

  def GetDataRoot(self):
    """Returns the directory for persistent data."""
    return '/var/factory'

  def _GetMountPointByDiskFree(self, path):
    """Returns a pair (mount_point, device) where path is mounted.

    Unlike GetMountPoint, path is directly passed to df even if it doesn't
    exist.
    """
    filesystems = self._dut.toybox.df(path)
    if not filesystems:
      logging.warn('cannot find mount point of %s', path)
      return None, None
    else:
      return filesystems[0].mounted_on, filesystems[0].filesystem

  def GetMountPoint(self, path):
    """Returns a pair (mount_point, device) where path is mounted.

    Since _GetMountPointByDiskFree will fail if path doesn't exist. We will drop
    each component in the path until new path exists. Then use
    _GetMountPointByDiskFree to get the mount point and device of new path.
    """
    while not self._dut.path.exists(path):
      new_path = self._dut.path.dirname(path)
      if new_path == path:
        break
      path = new_path

    return self._GetMountPointByDiskFree(path)

  def Remount(self, path, options="rw"):
    """Remount the file system of path with given options.

    Finds the mount point of file system which the given path belongs to, and
    then remount the file system with specified options.
    Useful for changing file system into write-able state, or to allow file
    execution.

    Args:
      path: A string for the path to re-mount.
      options: A string for the option to remount (passed to mount(1),
               defaults to 'rw').
    """

    mount_point, _ = self.GetMountPoint(path)
    if not mount_point:
      logging.error('remount: Cannot get mount point of %s', path)
      return False

    cmd = ['mount', '-o', 'remount,%s' % options, mount_point]
    if self._dut.Call(cmd) != 0:
      logging.error('remount: Cannot remount mount point: %s', mount_point)
      return False

    return True

  def GetMainStorageDevice(self):
    return self._dut.CheckOutput(['rootdev', '-d', '/usr/local']).strip()


class AndroidStorage(Storage):

  def GetMainStorageDevice(self):
    device = self.GetMountPoint('/data')[1]
    if not device:
      raise IOError('Unable to find main storage device (/usr/local)')
    return re.sub(r'p?(\d+)$', '', device)
