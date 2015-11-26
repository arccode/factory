# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Basic board specific interface."""

from __future__ import print_function

import factory_common  # pylint: disable=W0611
from cros.factory.system import SystemProperty
from cros.factory.test import dut as dut_module
from cros.factory.test.utils import Enum
from cros.factory.utils import type_utils


class BoardException(Exception):
  """Exception for Board class."""
  pass


class Board(object):
  """Abstract interface for board-specific functionality.

  This class provides an interface for board-specific functionality,
  such as forcing device charge state, forcing fan speeds, and
  observing on-board temperature sensors.  In general, these behaviors
  are implemented with low-level commands such as ``ectool``, so
  there may be no standard interface to them (e.g., via the ``/sys``
  filesystem).

  To obtain a :py:class:`cros.factory.system.board.Board` object for
  the device under test, use the
  :py:func:`cros.factory.system.GetBoard` function.

  Implementations of this interface should be in the
  :py:mod:`cros.factory.board` package.  One such implementation,
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard`, mostly
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

  All methods may raise a :py:class:`BoardException` on failure, or a
  :py:class:`NotImplementedException` if not implemented for this board.
  """

  Error = BoardException

  LEDColor = Enum(['AUTO', 'OFF', 'RED', 'GREEN', 'BLUE', 'YELLOW', 'WHITE'])
  """Charger LED colors.

  - ``AUTO``: Use the default logic to select the LED color.
  - ``OFF``: Turn the LED off.
  - others: The respective colors.
  """

  LEDIndex = Enum(['POWER', 'BATTERY', 'ADAPTER'])
  """LED names.

  - ``POWER``: Power LED.
  - ``BATTERY``: Battery LED.
  - ``ADAPTER``: Adapter LED.
  """

  AUTO = 'auto'
  """Constant representing automatic fan speed."""

  # Functions that are used in Goofy. Must be implemented.

  def __init__(self, dut=None):
    """Constructor.

    Arg:
      dut: A cros.factory.test.dut instance for accessing device under test.
    """
    if dut is None:
      dut = dut_module.Create()
    self.dut = dut

  def GetMainFWVersion(self):
    """Gets the main firmware version.

    Returns:
      A string of the main firmware version.
    """
    raise NotImplementedError

  # Optional functions. Implement them if you need them in your tests.
  def SetLEDColor(self, color, led_name='battery', brightness=100):
    """Sets LED color.

    Args:
      color: LED color of type LEDColor enum.
      led_name: target LED name.
      brightness: LED brightness in percentage [0, 100].
          If color is 'auto' or 'off', brightness is ignored.
    """
    raise NotImplementedError

  def GetBoardVersion(self):
    """Gets the version of the board (MLB).

    Returns:
      A string of the version of the MLB board, like::

        Proto2B
        EVT
        DVT

    Raises:
      BoardException if board version cannot be obtained.
    """
    raise NotImplementedError

  def OnTestStart(self):
    """Callback invoked when factory test starts.

    This method is called when goofy starts or when the operator
    starts a test manually. This can be used to light up a green
    LED or send a notification to a remote server.
    """
    pass

  def OnTestFailure(self, test):
    """Callback invoked when a test fails.

    This method can be used to bring the attention of the operators
    when a display is not available. For example, lightting up a red
    LED may help operators identify failing device on the run-in
    rack easily.
    """
    pass

  def OnSummaryGood(self):
    """Callback invoked when the test summary page shows and all test passed.

    This method can be used to notify the operator that a device has finished
    a test section, e.g. run-in. For example, lightting up a green LED here
    and the operators may be instructed to move all devices with a green LED
    to FATP testing.
    """
    pass

  def OnSummaryBad(self):
    """Callback invoked when the test summary page shows and some test failed.

    Similar to OnSummaryGood, but is used to notify the operator of failing
    test(s).
    """
    pass
