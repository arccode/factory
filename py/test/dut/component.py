# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Base class for DUT system components."""

from __future__ import print_function

import factory_common  # pylint: disable=W0611
from cros.factory.utils import type_utils


# Default component property - using lazy loaded property implementation.
DUTProperty = type_utils.LazyProperty


class DUTException(Exception):
  """Common exception for all components."""
  pass


class DUTComponent(object):
  """A base class for all system components running on DUT.

  All modules under cros.factory.test.dut (and usually a property of DUTBoard)
  should inherit DUTComponent.

  Example:

  class MyComponent(DUTComponent):

    @DUTProperty
    def controller(self):
      return MyController(self)

    def SomeFunction(self):
      return self._do_something()

  Attributes:
    _dut: A cros.factory.test.dut.board.DUTBoard instance for accessing DUT.
    Error: Exception type for raising unexpected errors.
  """

  def __init__(self, dut):
    self._dut = dut
