#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import tempfile


class CalledProcessError(subprocess.CalledProcessError):
  pass


class BaseTarget(object):
  """An abstract class for DUT (Device Under Test) Targets."""

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
    """
    raise NotImplementedError

  def Shell(self, command, stdin=None, stdout=None, stderr=None):
    """Executes a command on DUT.

    The calling convention is similar to subprocess.call, but only a subset of
    parameters are supported due to platform limitation.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.

    Returns:
      Exit code from executed command.
      If stdout, or stderr is not None, the output is stored in corresponding
      object.
    """
    raise NotImplementedError

  def IsReady(self):
    """Checks if DUT is ready for connection.

    Returns:
      A boolean indicating if target DUT is ready.
    """
    raise NotImplementedError

  def Call(self, command, stdin=None, stdout=None, stderr=None):
    """Executes a command on DUT, using subprocess.call convention.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.

    Returns:
      Exit code from executed command.
    """
    return self.Shell(command, stdin, stdout, stderr)

  def CheckCall(self, command, stdin=None, stdout=None, stderr=None):
    """Executes a command on DUT, using subprocess.check_call convention.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.

    Returns:
      Exit code from executed command.

    Raises:
      CalledProcessError if the exit code is non-zero.
    """
    exit_code = self.Call(command, stdin, stdout, stderr)
    if exit_code != 0:
      raise CalledProcessError(returncode=exit_code, cmd=command)
    return exit_code

  def CheckOutput(self, command, stdin=None, stderr=None):
    """Executes a command on DUT, using subprocess.check_output convention.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.

    Returns:
      The output on STDOUT from executed command.

    Raises:
      CalledProcessError if the exit code is non-zero.
    """
    with tempfile.TemporaryFile() as stdout:
      exit_code = self.Call(command, stdin, stdout, stderr)
      stdout.flush()
      stdout.seek(0)
      output = stdout.read()
    if exit_code != 0:
      raise CalledProcessError(
          returncode=exit_code, cmd=command, output=output)
    return output
