# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Base class for Device-Aware API components."""

from __future__ import print_function
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.utils import type_utils


# Default component property - using lazy loaded property implementation.
DeviceProperty = type_utils.LazyProperty

# Use subprocess.CalledProcessError for invocation exceptions.
CalledProcessError = subprocess.CalledProcessError


class DeviceException(Exception):
  """Common exception for all components."""
  pass


class DeviceComponent(object):
  """A base class for all system components available on device.

  All modules under cros.factory.device (and usually a property of DeviceBoard)
  should inherit DeviceComponent.

  Example:

  class MyComponent(DeviceComponent):

    @DeviceProperty
    def controller(self):
      return MyController(self)

    def SomeFunction(self):
      return self._do_something()

  Attributes:
    _board: A cros.factory.device.board.DeviceBoard instance for accessing device.
    Error: Exception type for raising unexpected errors.
  """

  Error = DeviceException

  def __init__(self, board):
    """Constructor of DeviceComponent.

    :type board: cros.factory.device.board.DeviceBoard
    """
    # TODO(hungte) Change _dut to some better name that reflects that it's a
    # board Device instance.
    self._dut = board


# Legacy names
DUTComponent = DeviceComponent
DUTException = DeviceException
DUTProperty = DeviceProperty
