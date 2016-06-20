# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic board specific interface."""

from __future__ import print_function
import glob
import logging
import subprocess
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.test.dut import component
from cros.factory.test.dut import hooks
from cros.factory.test.dut import utils


DUTProperty = component.DUTProperty
DUTException = component.DUTException
CalledProcessError = component.CalledProcessError


class DUTBoard(object):
  """Abstract interface for board-specific functionality.

  This class provides an interface for board-specific functionality,
  such as forcing device charge state, forcing fan speeds, and
  observing on-board temperature sensors.  In general, these behaviors
  are implemented with low-level commands such as ``ectool``, so
  there may be no standard interface to them (e.g., via the ``/sys``
  filesystem).

  To obtain a :py:class:`cros.factory.test.dut.board.DUTBoard` object for
  the device under test, use the
  :py:func:`cros.factory.test.dut.Create` function.

  Implementations of this interface should be in the
  :py:mod:`cros.factory.test.dut.boards` package.  One such implementation,
  :py:class:`cros.factory.test.dut.boards.chromeos.ChromeOSBoard`, mostly
  implements these behaviors using ``ectool``.  It is mostly concrete
  but may be further subclassed as necessary.

  In general, this class is only for functionality that may need to be
  implemented separately on a board-by-board basis.  If there is a
  standard system-level interface available for certain functionality
  (e.g., using a Python API, a binary available on all boards, or
  ``/sys``) then it should not be in this class, but rather wrapped in
  a class in the :py:mod:`cros.factory.system` module, or in a utility
  method in :py:mod:`cros.factory.utils`.  See
  :ref:`board-api-extending`.

  All methods may raise a :py:class:`DUTException` on failure, or a
  :py:class:`NotImplementedError` if not implemented for this board.

  Attributes:
    link: A cros.factory.test.dut.link.DUTLink instance for accessing DUT.
  """

  # Special values to make Popen work like subprocess.
  PIPE = subprocess.PIPE
  STDOUT = subprocess.STDOUT

  def __init__(self, dut_link=None):
    """Constructor.

    Arg:
      dut_link: A cros.factory.test.dut.link.DUTLink instance for accessing
                device under test.
    """
    self.link = utils.CreateLink() if dut_link is None else dut_link

  # Board modules and properties

  @DUTProperty
  def accelerometer(self):
    """Sensor measures proper acceleration (also known as g-sensor)."""
    raise NotImplementedError()

  @DUTProperty
  def audio(self):
    """Audio input and output, including headset, mic, and speakers."""
    raise NotImplementedError()

  @DUTProperty
  def bluetooth(self):
    """Interface to connect and control Bluetooth devices."""
    raise NotImplementedError()

  @DUTProperty
  def camera(self):
    """Interface to control camera devices."""
    raise NotImplementedError()

  @DUTProperty
  def display(self):
    """Interface for showing images or taking screenshot."""
    raise NotImplementedError()

  @DUTProperty
  def ec(self):
    """Module for controlling Embedded Controller."""
    raise NotImplementedError()

  @DUTProperty
  def gyroscope(self):
    """Gyroscope sensors."""
    raise NotImplementedError()

  @DUTProperty
  def hooks(self):
    """Utility class managing device-specific callbacks."""
    return hooks.DUTHooks(self)

  @DUTProperty
  def hwmon(self):
    """Hardware monitor devices."""
    raise NotImplementedError()

  @DUTProperty
  def i2c(self):
    """Module for accessing to slave devices on I2C bus."""
    raise NotImplementedError()

  @DUTProperty
  def info(self):
    """Module for static information about the system."""
    raise NotImplementedError()

  @DUTProperty
  def init(self):
    """Module for adding / removing start-up jobs."""
    raise NotImplementedError()

  @DUTProperty
  def led(self):
    """Module for controlling LED."""
    raise NotImplementedError()

  @DUTProperty
  def memory(self):
    """Module for memory information."""
    raise NotImplementedError()

  @DUTProperty
  def partitions(self):
    """Provide information of partitions on a device."""
    raise NotImplementedError()

  @DUTProperty
  def wifi(self):
    """Interface for controlling WiFi devices."""
    raise NotImplementedError()

  @DUTProperty
  def path(self):
    """Provies operations on pathnames, similar to os.path."""
    raise NotImplementedError()

  @DUTProperty
  def power(self):
    """Interface for reading and controlling battery."""
    raise NotImplementedError()

  @DUTProperty
  def status(self):
    """Returns live system status (dynamic data like CPU loading)."""
    raise NotImplementedError()

  @DUTProperty
  def storage(self):
    """Information of the persistent storage on DUT."""
    raise NotImplementedError()

  @DUTProperty
  def temp(self):
    """Provides access to temporary files and directories."""
    raise NotImplementedError()

  @DUTProperty
  def thermal(self):
    """System module for thermal control (temperature sensors, fans)."""
    raise NotImplementedError()

  @DUTProperty
  def toybox(self):
    """A python wrapper for http://www.landley.net/toybox/."""
    raise NotImplementedError()

  @DUTProperty
  def touchscreen(self):
    """Module for touchscreen."""
    raise NotImplementedError()

  @DUTProperty
  def udev(self):
    """Module for detecting udev event."""
    raise NotImplementedError()

  @DUTProperty
  def usb_c(self):
    """System module for USB type-C."""
    raise NotImplementedError()

  @DUTProperty
  def vpd(self):
    """Interface for read / write Vital Product Data (VPD)."""
    raise NotImplementedError()

  # Helper functions to access DUT via link.

  def IsReady(self):
    """Backward-compatible call for DUTLink.IsReady."""
    return self.link.IsReady()

  def ReadFile(self, path, count=None, skip=None):
    """Returns file contents on DUT.

    By default the "most-efficient" way of reading file will be used, which may
    not work for special files like device node or disk block file. Use
    ReadSpecialFile for those files instead.

    Meanwhile, if count or skip is specified, the file will also be fetched by
    ReadSpecialFile.

    Args:
      path: A string for file path on DUT.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.

    Returns:
      A string as file contents.
    """
    if count is None and skip is None:
      return self.link.Pull(path)
    return self.ReadSpecialFile(path, count=count, skip=skip)

  def ReadSpecialFile(self, path, count=None, skip=None):
    """Returns contents of special file on DUT.

    Reads special files (device node, disk block, or sys driver files) on DUT
    using the most portable approach.

    Args:
      path: A string for file path on DUT.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.

    Returns:
      A string as file contents.
    """
    if self.link.IsLocal():
      with open(path, 'rb') as f:
        f.seek(skip or 0)
        return f.read() if count is None else f.read(count)

    args = ['dd', 'bs=1', 'if=%s' % path]
    if count is not None:
      args += ['count=%d' % count]
    if skip is not None:
      args += ['skip=%d' % skip]

    return self.CheckOutput(args)

  def WriteFile(self, path, content):
    """Writes some content into file on DUT.

    Args:
      path: A string for file path on DUT.
      content: A string to be written into file.
    """
    # If the link is local, we just open file and write content.
    if self.link.IsLocal():
      with open(path, 'w') as f:
        f.write(content)
      return

    with file_utils.UnopenedTemporaryFile() as temp_path:
      with open(temp_path, 'w') as f:
        f.write(content)
      self.link.Push(temp_path, path)

  def SendDirectory(self, local, remote):
    """Copies a local file to DUT.

    `local` should be a local directory, and `remote` should be a non-existing
    file path on DUT.

    Example::

        dut.SendDirectory('/path/to/local/dir', '/remote/path/to/some_dir')

      Will create directory `some_dir` under `/remote/path/to` and copy
      files and directories under `/path/to/local/dir/` to `some_dir`.

    Args:
      local: A string for directory path in local.
      remote: A string for directory path on remote DUT.
    """
    return self.link.PushDirectory(local, remote)

  def SendFile(self, local, remote):
    """Copies a local file to DUT.

    Args:
      local: A string for file path in local.
      remote: A string for file path on remote DUT.
    """
    return self.link.Push(local, remote)

  def Popen(self, command, stdin=None, stdout=None, stderr=None, log=False):
    """Executes a command on DUT using subprocess.Popen convention.

    This function should be the single entry point for invoking link.Shell
    because boards that need customization to shell execution (for example,
    adding PATH or TMPDIR) will override this.

    Args:
      command: A string or a list of strings for command to execute.
      stdin: A file object to override standard input.
      stdout: A file object to override standard output.
      stderr: A file object to override standard error.
      log: True (for logging.info) or a logger object to keep logs before
          running the command.

    Returns:
      An object similiar to subprocess.Popen (see link.Shell).
    """
    if log:
      logger = logging.info if log is True else log
      logger('%s Running: %r', type(self), command)
    return self.link.Shell(command, stdin, stdout, stderr)

  def Call(self, *args, **kargs):
    """Executes a command on DUT, using subprocess.call convention.

    The arguments are explained in Popen.

    Returns:
      Exit code from executed command.
    """
    process = self.Popen(*args, **kargs)
    process.wait()
    return process.returncode

  def CheckCall(self, command, stdin=None, stdout=None, stderr=None, log=False):
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
    exit_code = self.Call(command, stdin, stdout, stderr, log)
    if exit_code != 0:
      raise CalledProcessError(returncode=exit_code, cmd=command)
    return exit_code

  def CheckOutput(self, command, stdin=None, stderr=None, log=False):
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
      exit_code = self.Call(command, stdin, stdout, stderr, log)
      stdout.flush()
      stdout.seek(0)
      output = stdout.read()
    if exit_code != 0:
      raise CalledProcessError(
          returncode=exit_code, cmd=command, output=output)
    return output

  def CallOutput(self, *args, **kargs):
    """Runs the command on DUT and return data from standard output if success.

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
    """Finds files on DUT by pattern, similar to glob.glob.

    Args:
      pattern: A file path pattern (allows wild-card '*' and '?).

    Returns:
      A list of files matching pattern on DUT.
    """
    if self.link.IsLocal():
      return glob.glob(pattern)
    results = self.CallOutput('ls -d %s' % pattern)
    return results.splitlines() if results else []
