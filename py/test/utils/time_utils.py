#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime

import factory_common  # pylint: disable=unused-import
from cros.factory.test import dut as dut_module


def SyncDate(dut=None):
  """Sync DUT datetime with station.

  Args:
    :type dut: cros.factory.test.dut.board.DUTBoard
  """

  if not dut:
    dut = dut_module.Create()

  if not dut.link.IsLocal():
    now = datetime.datetime.utcnow()
    # set DUT time
    dut.CheckCall(
        ['date', '-u', '{:%m%d%H%M%Y.%S}'.format(now)], log=True)
