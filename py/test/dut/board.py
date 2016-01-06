# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic board specific interface."""

from __future__ import print_function
import glob
import tempfile

# Assume most DUTs will be running POSIX os.
import posixpath

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import accelerometer
from cros.factory.test.dut.audio import utils as audio_utils
from cros.factory.test.dut import bluetooth
from cros.factory.test.dut import component
from cros.factory.test.dut import display
from cros.factory.test.dut import ec
from cros.factory.test.dut import hooks
from cros.factory.test.dut import i2c
from cros.factory.test.dut import info
from cros.factory.test.dut import led
from cros.factory.test.dut import path as path_module
from cros.factory.test.dut import partitions
from cros.factory.test.dut import power
from cros.factory.test.dut import status
from cros.factory.test.dut import storage
from cros.factory.test.dut import temp
from cros.factory.test.dut import thermal
from cros.factory.test.dut import udev
from cros.factory.test.dut import utils
from cros.factory.test.dut import vpd
from cros.factory.utils import file_utils


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
    return accelerometer.Accelerometer(self)

  @DUTProperty
  def bluetooth(self):
    return bluetooth.BluetoothManager(self)

  @DUTProperty
  def audio(self):
    # Override this property in sub-classed boards to specify different audio
    # config path if required.
    return audio_utils.CreateAudioControl(self)

  @DUTProperty
  def display(self):
    return display.Display(self)

  @DUTProperty
  def ec(self):
    return ec.EmbeddedController(self)

  @DUTProperty
  def hooks(self):
    return hooks.DUTHooks(self)

  @DUTProperty
  def i2c(self):
    return i2c.I2CBus(self)

  @DUTProperty
  def info(self):
    return info.SystemInfo(self)

  @DUTProperty
  def led(self):
    return led.LED(self)

  @DUTProperty
  def partitions(self):
    """Returns the partition names of system boot disk."""
    return partitions.Partitions(self)

  @DUTProperty
  def path(self):
    """Returns a module to handle path operations.

    If self.link.IsLocal() == True, then module posixpath is returned,
    otherwise, self._RemotePath is returned.
    If you only need to change the implementation of remote DUT, try to override
    _RemotePath.
    """
    if self.link.IsLocal():
      return posixpath
    return self._RemotePath

  @DUTProperty
  def _RemotePath(self):
    """Returns a module to handle path operations on remote DUT.

    self.path will return this object if DUT is not local. Override this to
    change the implementation of remote DUT.
    """
    return path_module.Path(self)

  @DUTProperty
  def power(self):
    return power.Power(self)

  @DUTProperty
  def temp(self):
    return temp.TemporaryFiles(self)

  @DUTProperty
  def storage(self):
    return storage.Storage(self)

  @DUTProperty
  def thermal(self):
    return thermal.Thermal(self)

  @DUTProperty
  def vpd(self):
    return vpd.VitalProductData(self)

  @DUTProperty
  def status(self):
    """Returns live system status (dynamic data like CPU loading)."""
    return status.SystemStatus(self)

  @DUTProperty
  def udev(self):
    return udev.LocalUdevMonitor(self)

  # Helper functions to access DUT via link.

  def IsReady(self):
    """Backward-compatible call for DUTLink.IsReady."""
    return self.link.IsReady()

  def ReadFile(self, path, count=None, skip=None):
    """Returns file contents on DUT.

    By default the "most-efficient" way of reading file will be used, but that
    may not work for special files like device node or disk block file. You can
    specify count or skip to read special files, for example:

      kern_blob = dut.ReadFile('/dev/sda2', skip=0)

    Args:
      path: A string for file path on DUT.
      count: Number of bytes to read. None to read whole file.
      skip: Number of bytes to skip before reading. None to read from beginning.

    Returns:
      A string as file contents.
    """
    if count is None and skip is None:
      return self.link.Pull(path)

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
    with file_utils.UnopenedTemporaryFile() as temp_path:
      with open(temp_path, 'w') as f:
        f.write(content)
      self.link.Push(temp_path, path)

  def SendFile(self, local, remote):
    """Copies a local file to DUT.

    Args:
      local: A string for file path in local.
      remote: A string for file path on remote DUT.
    """
    return self.link.Push(local, remote)

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
    return self.link.Shell(command, stdin, stdout, stderr)

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
