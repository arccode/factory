# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to call a shopfloor method.

The test may also perform an action based on the return value.
See RETURN_VALUE_ACTIONS for the list of possible actions.
"""


import logging
import types
import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test import factory, shopfloor
from cros.factory.test.args import Arg


def UpdateDeviceData(data):
  shopfloor.UpdateDeviceData(data)
  factory.get_state_instance().UpdateSkippedTests()


class CallShopfloor(unittest.TestCase):
  # Possible values for the "action" handler
  RETURN_VALUE_ACTIONS = {
      # Update device data with the returned dictionary.
      'update_device_data': UpdateDeviceData
  }

  ARGS = [
    Arg('method', str,
        'Name of shopfloor method to call'),
    Arg('args', (list, types.FunctionType),
        'Method arguments'),
    Arg('action', str,
        ('Action to perform with return value; one of %s' %
         sorted(RETURN_VALUE_ACTIONS.keys())),
        optional=True),
  ]

  def runTest(self):
    if self.args.action:
      action_handler = self.RETURN_VALUE_ACTIONS.get(self.args.action)
      self.assertTrue(
          action_handler,
          'Invalid action %r; should be one of %r' % (
              self.args.action, sorted(self.RETURN_VALUE_ACTIONS.keys())))
    else:
      action_handler = lambda value: None

    method = getattr(shopfloor.get_instance(detect=True), self.args.method)
    logging.info('Invoking %s(%s)',
                 self.args.method, ', '.join(repr(x) for x in self.args.args))

    action_handler(method(*self.args.args))
