# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic board specific interface."""

from __future__ import print_function
import glob
import os
import subprocess
import tempfile

# Assume most DUTs will be running POSIX os.
import posixpath

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import accelerometer
from cros.factory.test.dut import component
from cros.factory.test.dut import ec
from cros.factory.test.dut.links import utils as link_utils
from cros.factory.test.dut import power
from cros.factory.test.dut import temp
from cros.factory.test.dut import thermal
from cros.factory.test.dut import vpd
from cros.factory.utils import file_utils


DUTProperty = component.DUTProperty
DUTException = component.DUTException
CalledProcessError = subprocess.CalledProcessError


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
    if dut_link is None:
      dut_link = link_utils.Create()
    self.link = dut_link

  # Board modules and properties

  @DUTProperty
  def accelerometer(self):
    return accelerometer.Accelerometer(self)

  @DUTProperty
  def ec(self):
    return ec.EmbeddedController(self)

  @DUTProperty
  def path(self):
    """Default 'path' that provides os.path functions."""
    # TODO(hungte) Currently this is only safe for functions not accessing DUT,
    # for example join and split. Need to change this into a new module
    # providing functions that will access DUT, for example exists, isdir, ...
    return posixpath

  @DUTProperty
  def power(self):
    return power.Power(self)

  @DUTProperty
  def temp(self):
    return temp.TemporaryFiles(self)

  @DUTProperty
  def thermal(self):
    return thermal.Thermal(self)

  @DUTProperty
  def vpd(self):
    return vpd.VitalProductData(self)

  # Helper functions to access DUT via link.

  def IsReady(self):
    """Backward-compatible call for DUTLink.IsReady."""
    return self.link.IsReady()

  def ReadFile(self, path):
    """Returns file content on DUT.

    Args:
      path: A string for file path on DUT.

    Returns:
      A string as file contents.
    """
    return self.link.Pull(path)

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

  def FileExists(self, path):
    """Checks if a path exists on DUT.

    Args:
      path: A string of file path.
    """
    if self.link.IsLocal():
      return os.path.exists(path)
    return self.Call(['test', '-e', path]) == 0

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


def Create(dut_link=None):
  """Returns a board instance for the device under test.

  By default, a
  :py:class:`cros.factory.test.dut.board.DUTBoard` object
  is returned, but this may be overridden by setting the
  ``CROS_FACTORY_DUT_BOARD_CLASS`` environment variable in
  ``board_setup_factory.sh``.  See :ref:`board-api-extending`.

  Parameters:
    dut_link: A :py:class:`cros.factory.test.dut.link.DUTLink` object or None.

  Returns:
    An instance of the specified DUTBoard class implementation.
  """
  board = os.environ.get('CROS_FACTORY_DUT_BOARD_CLASS',
                         'cros.factory.test.dut.board.DUTBoard')
  module, cls = board.rsplit('.', 1)
  _board = getattr(__import__(module, fromlist=[cls]), cls)(dut_link)
  return _board
