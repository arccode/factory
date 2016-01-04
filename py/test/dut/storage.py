#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing access to permanet storage on DUT"""

import logging
import re
from subprocess import CalledProcessError

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

    # Get mount point of file system
    # TODO(stimim): implement this by 'readlink' or 'realpath'
    try:
      # the output should look like:
      # Mounted on
      # /usr/local
      output = self._dut.CheckOutput(['df', '--output=target', path])
    except CalledProcessError:
      logging.exception('remount: Cannot get mount point of %s', path)
      return False

    match = re.search(r'^(/[/\w]+)$', output, re.MULTILINE)
    if not match:
      logging.error('remount: The output of df is unexpected:\n%s', output)
      return False

    mount_point = match.group(1)

    cmd = ['mount', '-o', 'remount,%s' % options, mount_point]
    if self._dut.Call(cmd) != 0:
      logging.error('remount: Cannot remount mount point: %s', mount_point)
      return False

    return True

