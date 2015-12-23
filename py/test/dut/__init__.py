#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.test.dut import component
from cros.factory.test.dut import utils


# Forward the exception for easy access to all DUT (board, component)
# exceptions.
DUTException = component.DUTException

# Forward the correct DUT object factory.
Create = utils.CreateBoard
