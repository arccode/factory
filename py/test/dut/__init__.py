#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.test.dut.links import utils as link_utils
from cros.factory.test.dut import board
from cros.factory.test.dut import component


# Forward the exception for easy access to all DUT (board, component)
# exceptions.
DUTException = component.DUTException


def Create(**kargs):
  """Creates a DUT instance by given options."""
  # TODO(hungte) Allow creating different board class in kargs.
  return board.Create(link_utils.Create(**kargs))
