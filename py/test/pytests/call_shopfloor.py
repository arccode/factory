# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to call a shopfloor method.

The test may also perform an action based on the return value.
See RETURN_VALUE_ACTIONS for the list of possible actions.
"""


import logging
import threading
import types
import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.privacy import FilterDict
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import WaitEvent


def UpdateDeviceData(data):
  shopfloor.UpdateDeviceData(data)
  factory.get_state_instance().UpdateSkippedTests()
  Log('update_device_data', data=FilterDict(data))


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

  def setUp(self):
    self.done = False
    self.event = threading.Event()

  def runTest(self):
    if self.args.action:
      action_handler = self.RETURN_VALUE_ACTIONS.get(self.args.action)
      self.assertTrue(
          action_handler,
          'Invalid action %r; should be one of %r' % (
              self.args.action, sorted(self.RETURN_VALUE_ACTIONS.keys())))
    else:
      action_handler = lambda value: None

    ui = test_ui.UI()
    def Done():
      self.done = True
      self.event.set()

    ui.Run(blocking=False, on_finish=Done)
    ui.AppendCSS('.large { font-size: 200% }')
    template = ui_templates.OneSection(ui)

    ui.AddEventHandler('retry', lambda dummy_event: self.event.set())

    while not self.done:
      method = getattr(shopfloor.get_instance(detect=True), self.args.method)
      message = 'Invoking %s(%s)' % (
          self.args.method, ', '.join(repr(x) for x in self.args.args))
      logging.info(message)
      template.SetState(test_ui.Escape(message))

      try:
        action_handler(method(*self.args.args))
        break
      except:  # pylint: disable=W0702
        logging.exception('Exception invoking shop floor method')
        template.SetState(
            test_ui.MakeLabel('Shop floor exception:',
                              'Shop floor 错误:',
                              'test-status-failed large') +
            '<p>' +
            utils.FormatExceptionOnly() +

            '<p><br>' +
            """<button onclick="test.sendTestEvent('retry')">""" +
            test_ui.MakeLabel('Retry', '重试') +
            '</button>'
            )
        WaitEvent(self.event)
        self.event.clear()

