#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.utils import time_utils as test_time_utils
from cros.factory.utils import time_utils
from cros.factory.utils.arg_utils import Arg


class SyncTime(unittest.TestCase):

  ARGS = [
      Arg('tolerance', float,
          'Max absolute time difference between DUT and station after sync.',
          default=5.0, optional=True)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    factory.console.info('DUT time was: %s',
                         self.dut.CallOutput(['date', '-u'], log=True))

    test_time_utils.SyncDate(self.dut)

    dut_now = float(self.dut.CallOutput(['date', '-u', '+%s'], log=True))
    goofy_now = (datetime.datetime.utcnow() -
                 time_utils.EPOCH_ZERO).total_seconds()

    self.assertAlmostEqual(goofy_now, dut_now, delta=self.args.tolerance)
