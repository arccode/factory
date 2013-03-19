# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Manually updates device data."""


import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test.args import Arg


class CallShopfloor(unittest.TestCase):
  ARGS = [
    Arg('data', dict,
        'Items to update in device data dict.'),
  ]

  def runTest(self):
    shopfloor.UpdateDeviceData(self.args.data)
    factory.get_state_instance().UpdateSkippedTests()
