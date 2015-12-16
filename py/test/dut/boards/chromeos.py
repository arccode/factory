#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS family boards."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import board


class ChromeOSBoard(board.DUTBoard):
  """Common interface for ChromeOS boards."""
  pass
