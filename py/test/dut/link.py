#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


class DUTLink(object):
  """An abstract class for DUT (Device Under Test) Links."""

  def Push(self, local, remote):
    """Uploads a local file to DUT.

    Args:
      local: A string for local file path.
      remote: A string for remote file path on DUT.
    """
    raise NotImplementedError

  def Pull(self, remote, local=None):
    """Downloads a file from DUT to local.

    Args:
      remote: A string for file path on remote DUT.
      local: A string for local file path to receive downloaded content, or
             None to return the contents directly.

    Returns:
      If local is None, return a string as contents in remote file.
      Otherwise, do not return anything.
    """
    raise NotImplementedError

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """Executes a command on DUT.

    The calling convention is similar to subprocess.Popen, but only a subset of
    parameters are supported due to platform limitation.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.

    Returns:
      An object representing the process, similar to subprocess.Popen.
    """
    raise NotImplementedError

  def IsReady(self):
    """Checks if DUT is ready for connection.

    Returns:
      A boolean indicating if target DUT is ready.
    """
    raise NotImplementedError

  def IsLocal(self):
    """Returns if the test is running locally on DUT.

    This is helpful for tests to decide if they can use Python native modules or
    need to invoke system commands.
    """
    return False

  @classmethod
  def PrepareLink(cls):
    """Setup prerequisites of DUT connections.

    Some DUT types need to do some setup before we can connect to any DUT.
    For example, we might need to start a DHCP server that assigns IP addresses
    to DUTs.
    """
    pass
