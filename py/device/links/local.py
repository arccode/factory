# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of cros.factory.device.device_types.DeviceLink on local
system."""

import pipes
import shutil
import subprocess

from cros.factory.device import device_types


class LocalLink(device_types.DeviceLink):
  """Runs locally on a device."""

  def __init__(self, shell_path=None):
    """Link constructor.

    Args:
      shell_path: A string for the path of default shell.
    """
    self._shell_path = shell_path

  def Push(self, local, remote):
    """See DeviceLink.Push"""
    shutil.copy(local, remote)

  def PushDirectory(self, local, remote):
    """See DeviceLink.PushDirectory"""
    shutil.copytree(local, remote)

  def Pull(self, remote, local=None):
    """See DeviceLink.Pull"""
    if local is None:
      with open(remote) as f:
        return f.read()
    shutil.copy(remote, local)
    return None

  def Shell(self, command, stdin=None, stdout=None, stderr=None, cwd=None,
            encoding='utf-8'):
    """See DeviceLink.Shell"""

    # On most remote links, we always need to execute the commands via shell. To
    # unify the behavior we should always run the command using shell even on
    # local links. Ideally python should find the right shell intepreter for us,
    # however at least in Python 2.x, it was unfortunately hard-coded as
    # (['/bin/sh', '-c'] + args) when shell=True. In other words, if your
    # default shell is not sh or if it is in other location (for instance,
    # Android only has /system/bin/sh) then calling Popen may give you 'No such
    # file or directory' error.

    if not isinstance(command, str):
      command = ' '.join(pipes.quote(param) for param in command)

    if self._shell_path:
      # Shell path is specified and we have to quote explicitly.
      command = [self._shell_path, '-c', command]
      shell = False
    else:
      # Trust default path specified by Python runtime. Useful for non-POSIX
      # systems like Windows.
      shell = True
    return subprocess.Popen(command, shell=shell, cwd=cwd, close_fds=True,
                            stdin=stdin, stdout=stdout, stderr=stderr,
                            encoding=encoding)

  def IsReady(self):
    """See DeviceLink.IsReady"""
    return True

  def IsLocal(self):
    """See DeviceLink.IsLocal"""
    return True
