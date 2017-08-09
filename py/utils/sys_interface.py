# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The abstraction of minimal functions needed to access a system."""

import glob
import logging
import pipes
import shutil
import subprocess
import tempfile


# Use subprocess.CalledProcessError for invocation exceptions.
CalledProcessError = subprocess.CalledProcessError


class SystemInterface(object):
  """Abstract interface for accessing a system."""

  # Special values to make Popen work like subprocess.
  PIPE = subprocess.PIPE
  STDOUT = subprocess.STDOUT
  CalledProcessError = subprocess.CalledProcessError

  def ReadFile(self, path, count=None, skip=None):
    """Returns file contents on target device.

    By default the "most-efficient" way of reading file will be used, which may
    not work for special files like device node or disk block file. Use
    ReadSpecialFile for those files instead.

    Meanwhile, if count or skip is specified, the file will also be fetched by
    ReadSpecialFile.

    Args:
      path: A string for file path on target device.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.

    Returns:
      A string as file contents.
    """
    if count is None and skip is None:
      with open(path) as f:
        return f.read()
    return self.ReadSpecialFile(path, count=count, skip=skip)

  def ReadSpecialFile(self, path, count=None, skip=None):
    """Returns contents of special file on target device.

    Reads special files (device node, disk block, or sys driver files) on device
    using the most portable approach.

    Args:
      path: A string for file path on target device.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.

    Returns:
      A string as file contents.
    """
    with open(path, 'rb') as f:
      if skip:
        try:
          f.seek(skip)
        except IOError:
          f.read(skip)
      return f.read() if count is None else f.read(count)

  def WriteFile(self, path, content):
    """Writes some content into file on target device.

    Args:
      path: A string for file path on target device.
      content: A string to be written into file.
    """
    with open(path, 'w') as f:
      return f.write(content)

  def WriteSpecialFile(self, path, content):
    """Writes some content into a special file on target device.

    Args:
      path: A string for file path on target device.
      content: A string to be written into file.
    """
    return self.WriteFile(path, content)

  def SendDirectory(self, local, remote):
    """Copies a local directory to target device.

    `local` should be a local directory, and `remote` should be a non-existing
    file path on target device.

    Example::

    SendDirectory('/path/to/local/dir', '/remote/path/to/some_dir')

    Will create directory `some_dir` under `/remote/path/to` and copy
    files and directories under `/path/to/local/dir/` to `some_dir`.

    Args:
      local: A string for directory path in local.
      remote: A string for directory path on remote device.
    """
    return shutil.copytree(local, remote)

  def SendFile(self, local, remote):
    """Copies a local file to target device.

    Args:
      local: A string for file path in local.
      remote: A string for file path on remote device.
    """
    return shutil.copy(local, remote)

  def Popen(self, command, stdin=None, stdout=None, stderr=None, log=False):
    """Executes a command on target device using subprocess.Popen convention.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.
      log: True (for logging.info) or a logger object to keep logs before
          running the command.

    Returns:
      An object similar to subprocess.Popen.
    """
    if log:
      logger = logging.info if log is True else log
      logger('%s Running: %r', type(self), command)

    if not isinstance(command, basestring):
      command = ' '.join(pipes.quote(param) for param in command)
    return subprocess.Popen(command, shell=True, close_fds=True, stdin=stdin,
                            stdout=stdout, stderr=stderr)

  def Call(self, *args, **kargs):
    """Executes a command on target device, using subprocess.call convention.

    The arguments are explained in Popen.

    Returns:
      Exit code from executed command.
    """
    process = self.Popen(*args, **kargs)
    process.wait()
    return process.returncode

  def CheckCall(self, command, stdin=None, stdout=None, stderr=None, log=False):
    """Executes a command on device, using subprocess.check_call convention.

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
    exit_code = self.Call(command, stdin, stdout, stderr, log)
    if exit_code != 0:
      raise CalledProcessError(returncode=exit_code, cmd=command)
    return exit_code

  def CheckOutput(self, command, stdin=None, stderr=None, log=False):
    """Executes a command on device, using subprocess.check_output convention.

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
      exit_code = self.Call(command, stdin, stdout, stderr, log)
      stdout.flush()
      stdout.seek(0)
      output = stdout.read()
    if exit_code != 0:
      raise CalledProcessError(
          returncode=exit_code, cmd=command, output=output)
    return output

  def CallOutput(self, *args, **kargs):
    """Runs the command on device and returns standard output if success.

    Returns:
      If command exits with zero (success), return the standard output;
      otherwise None. If the command didn't output anything then the result is
      empty string.
    """
    try:
      return self.CheckOutput(*args, **kargs)
    except CalledProcessError:
      return None

  def Glob(self, pattern):
    """Finds files on target device by pattern, similar to glob.glob.

    Args:
      pattern: A file path pattern (allows wild-card '*' and '?).

    Returns:
      A list of files matching pattern on target device.
    """
    return glob.glob(pattern)