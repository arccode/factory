# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test to call a shopfloor method.

The test may also perform an action based on the return value.
See RETURN_VALUE_ACTIONS for the list of possible actions.
"""


import logging
import threading
import unittest
import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.rules import privacy
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import process_utils


def UpdateDeviceData(data):
  shopfloor.UpdateDeviceData(data)
  event_log.Log('update_device_data', data=privacy.FilterDict(data))


def UpdateFactorySharedData(data):
  key, value = data.items()[0]
  state.set_shared_data(key, value)
  factory.console.info('%s: %s', key, value)
  event_log.Log('update_factory_shared_data', data=data)


def UpdateFactorySharedDataWithKeyAndListData(data, key, filter_index):
  """Apply a filter on the incoming data, and make a dictionary
  with the specified key and filtered data.
  """
  UpdateFactorySharedData({key: data[filter_index]})


class CallShopfloor(unittest.TestCase):
  # Possible values for the "action" handler
  RETURN_VALUE_ACTIONS = {
      # Update device data with the returned dictionary.
      'update_device_data': UpdateDeviceData,
      # set factory shared data
      'update_factory_shared_data': UpdateFactorySharedData,
      'update_factory_shared_data_with_key_and_list_data':
          UpdateFactorySharedDataWithKeyAndListData,
  }

  ARGS = [
      Arg('method', str,
          'Name of shopfloor method to call'),
      Arg('server_proxy_url', str,
          'the server_proxy_url for the shopfloor server',
          default='', optional=True),
      Arg('args', list,
          'Method arguments.  If any argument is a function, it will be '
          'invoked.'),
      Arg('action', str,
          ('Action to perform with return value; one of %s' %
           sorted(RETURN_VALUE_ACTIONS.keys())),
          optional=True),
      Arg('action_args', dict,
          'Action arguments.',
          default=None, optional=True),
  ]

  def setUp(self):
    self.done = False
    self.event = threading.Event()
    self.ui = test_ui.UI()
    self.ui.AppendCSS('.large { font-size: 200% }')
    self.template = ui_templates.OneSection(self.ui)

  def Done(self):
    self.done = True
    self.event.set()

  def runTest(self):
    self.ui.RunInBackground(self._runTest)
    self.ui.Run(on_finish=self.Done)

  def _runTest(self):
    if self.args.action:
      action_handler = self.RETURN_VALUE_ACTIONS.get(self.args.action)
      self.assertTrue(
          action_handler,
          'Invalid action %r; should be one of %r' % (
              self.args.action, sorted(self.RETURN_VALUE_ACTIONS.keys())))
    else:
      action_handler = lambda value: None

    self.ui.AddEventHandler('retry', lambda dummy_event: self.event.set())

    while not self.done:
      # If the server_proxy_url has been specified, create a simple XML-PRC
      # server. This applies to the scenario where an umpire server is not
      # set up.
      if bool(self.args.server_proxy_url):
        server_proxy = xmlrpclib.ServerProxy(self.args.server_proxy_url,
                                             allow_none=True)
      else:
        server_proxy = shopfloor.get_instance(detect=True)
      method = getattr(server_proxy, self.args.method)

      args_to_log = privacy.FilterDict(self.args.args)
      message = 'Invoking %s(%s)' % (
          self.args.method, ', '.join(repr(x) for x in args_to_log))

      logging.info(message)
      self.template.SetState(test_ui.Escape(message))

      # If any arguments are callable, evaluate them.
      args = [x() if callable(x) else x
              for x in self.args.args]

      def HandleError(trace):
        self.template.SetState(
            i18n_test_ui.MakeI18nLabelWithClass(
                'Shop floor exception:',
                'test-status-failed large') + '<p>' + test_ui.Escape(trace) +
            '<p><br>' + """<button onclick="test.sendTestEvent('retry')">""" +
            i18n_test_ui.MakeI18nLabel('Retry') + '</button>')
        process_utils.WaitEvent(self.event)
        self.event.clear()

      try:
        result = method(*args)
        event_log.Log('call_shopfloor',
                      method=self.args.method, args=args_to_log,
                      result=privacy.FilterDict(result))
      except:  # pylint: disable=bare-except
        logging.exception('Exception invoking shop floor method')

        exception_str = debug_utils.FormatExceptionOnly()
        event_log.Log('call_shopfloor',
                      method=self.args.method,
                      args=args_to_log, exception=exception_str)
        HandleError(exception_str)
        continue

      try:
        if self.args.action_args is None:
          action_handler(result)
        else:
          # See UpdateFactorySharedDataWithKeyAndListData() about
          # using action_args.
          action_handler(result, **self.args.action_args)
        break  # All done
      except:  # pylint: disable=bare-except
        logging.exception('Exception in action handler')
        HandleError(debug_utils.FormatExceptionOnly())
        # Fall through and retry
