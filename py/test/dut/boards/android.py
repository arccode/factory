#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android family boards."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import board
from cros.factory.test.dut import component
from cros.factory.test.dut import path
from cros.factory.test.dut import storage
from cros.factory.test.dut import temp
from cros.factory.test.dut import thermal


class AndroidBoard(board.DUTBoard):
  """Common interface for Android boards."""

  @component.DUTProperty
  def temp(self):
    return temp.AndroidTemporaryFiles(self)

  @component.DUTProperty
  def _RemotePath(self):
    return path.AndroidPath(self)

  @component.DUTProperty
  def storage(self):
    return storage.AndroidStorage(self)

  @component.DUTProperty
  def thermal(self):
    return thermal.SysFSThermal(self)
