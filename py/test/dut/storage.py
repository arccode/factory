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

    def _GetMountPointByDiskFree(path):
      # the output should look like:
      # Mounted on
      # /usr/local
      output = self._dut.CallOutput(['df', '--output=target', path])
      if not output:
        return None
      match = re.search(r'^(/[/\w]*)$', output, re.MULTILINE)
      if not match:
        logging.warning('remount: The output of df is unexpected:\n%s', output)
        return None
      return match.group(1)

    def _GetMountPointFromProcMounts(path):
      # resolve all symbolic links
      realpath = self._dut.path.realpath(path)
      logging.info('remount: %s is resolved to %s', path, realpath)

      output = self._dut.CallOutput('cat /proc/mounts')
      if not output:
        logging.error('remount: Cannot read /proc/mounts')
        return None

      # The format of /proc/mounts is documented in fstab(5),
      # second field of each line is the mount point
      mount_points = [x[1] for x in map(str.split, output.splitlines())]

      # '/' is always a mount point
      best_match = '/'
      for mount_point in mount_points:
        if (realpath.startswith(mount_point) and
            len(mount_point) > len(best_match)):
          best_match = mount_point
      return best_match

    mount_point = _GetMountPointByDiskFree(path)
    if not mount_point:
      logging.info('remount: Cannot get mount point by df, try /proc/mounts')
      mount_point = _GetMountPointFromProcMounts(path)

    if not mount_point:
      logging.error('remount: Cannot get mount point of %s', path)
      return False

    cmd = ['mount', '-o', 'remount,%s' % options, mount_point]
    if self._dut.Call(cmd) != 0:
      logging.error('remount: Cannot remount mount point: %s', mount_point)
      return False

    return True

