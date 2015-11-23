# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Interfaces to set and get system status and system information."""

from __future__ import print_function

import glob
import os
import threading

import factory_common  # pylint: disable=W0611
from cros.factory import test
from cros.factory.test.utils import ReadOneLine
from cros.factory.utils import type_utils

# pylint: disable=W0702
# Disable checking of exception types, since we catch all exceptions
# in many places.

_board = None
_lock = threading.Lock()

# Default system property - using lazy loaded property implementation.
SystemProperty = type_utils.LazyProperty


class SystemException(Exception):
  """Exception for system modules."""
  pass


class SystemModule(object):
  """A base class for all system modules for a board instance to use.

  All modules under cros.factory.system should inherit SystemModule.
  Example:

  class MyComponent(SystemModule):

    @SystemProperty
    def controller(self):
      return MyController(self)

    def SomeFunction(self):
      return self._do_something()

  Attributes:
    _board: A cros.factory.system.board instance for accessing DUT.
    Error: Exception type for raising unexpected errors.
  """

  Error = SystemException

  def __init__(self, board):
    self._board = board

  # DUT-friendly APIs
  def _Call(self, *args, **kargs):
    """Runs the command on DUT and return the exit code."""
    return self._board.dut.Call(*args, **kargs)

  def _CheckCall(self, *args, **kargs):
    """Runs the command on DUT and raise exception if exit code is not zero."""
    return self._board.dut.CheckCall(*args, **kargs)

  def _CheckOutput(self, *args, **kargs):
    """Runs the command on DUT and return data from standard output.

    Raises exception if exit code is not zero.
    """
    return self._board.dut.CheckOutput(*args, **kargs)

  def _CallOutput(self, *args, **kargs):
    """Runs the command on DUT and return data from standard output.

    Args:
      default: Default value to return on execution failure.

    Returns:
      Standard output of command if the execution success, or the value
      specified by 'default' argument (default to empty string).
    """
    try:
      return self._board.dut.CheckOutput(*args, **kargs)
    except:
      return kargs.get('default', '')

  def _Read(self, *args, **kargs):
    """Reads file using dut.Read."""
    return self._board.dut.Read(*args, **kargs)

  def _Write(self, *args, **kargs):
    """Writes file using dut.Write."""
    return self._board.dut.Write(*args, **kargs)

  def _Exists(self, path):
    """Checks if a path exists on DUT.

    Args:
      path: A string of file path.
    """
    return self._Call(['test', '-e', path]) == 0

  def _Glob(self, pattern):
    """Finds files on DUT by pattern, similar to glob.glob.

    Args:
      pattern: A file path pattern (allows wild-card '*' and '?).

    Returns:
      A list of files matching pattern on DUT.
    """
    # TODO(hungte) Use glob.glob if DUT is a local target.
    return self._CallOutput(['ls', pattern], default='').splitlines()


def GetBoard():
  """Returns a board instance for the device under test.

  By default, a
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard` object
  is returned, but this may be overridden by setting the
  ``CROS_FACTORY_BOARD_CLASS`` environment variable in
  ``board_setup_factory.sh``.  See :ref:`board-api-extending`.

  Returns:
    An instance of the specified Board class implementation.
  """
  # pylint: disable=W0603
  with _lock:
    global _board
    if _board:
      return _board

    board = os.environ.get('CROS_FACTORY_BOARD_CLASS',
                           'cros.factory.system.board.Board')
    module, cls = board.rsplit('.', 1)
    _board = getattr(__import__(module, fromlist=[cls]), cls)()
    return _board


# TODO(hungte) Move this to a new display module when we have finished the new
# system module migration.
def SetBacklightBrightness(level):
  """Sets the backlight brightness level.

  Args:
    level: A floating-point value in [0.0, 1.0] indicating the backlight
        brightness level.

  Raises:
    ValueError if the specified value is invalid.
  """
  if not (level >= 0.0 and level <= 1.0):
    raise ValueError('Invalid brightness level.')
  interfaces = glob.glob('/sys/class/backlight/*')
  for i in interfaces:
    with open(os.path.join(i, 'brightness'), 'w') as f:
      f.write('%d' % int(
          level * float(ReadOneLine(os.path.join(i, 'max_brightness')))))
