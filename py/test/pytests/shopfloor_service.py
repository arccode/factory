# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Invoke Shopfloor Service APIs.

For more information, see
https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/shopfloor/README.md
"""


import collections
import logging
import pprint
import threading
import unittest
import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.rules import privacy
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import process_utils
from cros.factory.utils import shelve_utils


class ServiceSpec(object):
  """The specification of shopfloor service API."""

  def __init__(self, has_data=True, auto_values=None, data_args=None,
               has_privacy_args=False):
    self.has_data = has_data
    self.has_privacy_args = has_privacy_args
    self.auto_values = auto_values or {}
    self.data_args = data_args


class ShopfloorService(unittest.TestCase):
  """Execution of remote shoploor service."""

  ARGS = [
      Arg('method', str,
          'Name of shopfloor service method to call'),
      Arg('args', (list, tuple), 'Arguments for specified method.',
          optional=True),
      Arg('server_url', str,
          'The URL to shopfloor service server', optional=True),
  ]

  # The expected value for GetVersion, to help checking server implementation.
  SERVICE_VERSION = '1.0'

  # Domain of values to exchange.
  DOMAIN_SERIALS = state.KEY_SERIALS
  DOMAIN_FACTORY = 'factory'
  DOMAIN_VPD = 'vpd'
  DOMAIN_COMPONENT = 'component'
  KEY_HWID = 'hwid'

  KEY_VPD_USER_ECHO = 'vpd.rw.ubind_attribute'
  KEY_VPD_GROUP_ECHO = 'vpd.rw.gbind_attribute'

  # Service API method names defined in version 1.0, in {name: has_data} format.
  METHODS = {
      'GetVersion': ServiceSpec(has_data=False),
      'NotifyStart': ServiceSpec(auto_values={'factory.start_{1}': True}),
      'NotifyEnd': ServiceSpec(auto_values={'factory.end_{1}': True}),
      'NotifyEvent': ServiceSpec(auto_values={'factory.event_{1}': True}),
      'GetDeviceInfo': ServiceSpec(),
      'ActivateRegCode': ServiceSpec(
          has_data=False, has_privacy_args=True,
          auto_values={'factory.activate_reg_code': True},
          data_args=[KEY_VPD_USER_ECHO, KEY_VPD_GROUP_ECHO, KEY_HWID]),
      'UpdateTestResult': ServiceSpec(),
  }

  def setUp(self):
    self.done = False
    self.dut = device_utils.CreateDUTInterface()
    self.event = threading.Event()
    self.ui = test_ui.UI()
    self.ui.AppendCSS('.large { font-size: 200% }')
    self.template = ui_templates.OneSection(self.ui)

  def runTest(self):
    self.ui.RunInBackground(self._runTest)
    self.ui.Run(on_finish=self.Done)

  def Done(self):
    self.done = True
    self.event.set()

  def FlattenData(self, data, parent=''):
    items = []
    for k, v in data.iteritems():
      new_key = shelve_utils.DictKey.Join(parent, k) if parent else k
      if isinstance(v, collections.Mapping):
        items.extend(self.FlattenData(v, new_key).items())
      else:
        items.append((new_key, v))
    return dict(items)

  def GetFactoryDeviceData(self):
    """Returns a dictionary in FactoryDeviceData format."""
    data = {}
    for domain in [self.DOMAIN_SERIALS, self.DOMAIN_FACTORY]:
      flat_data = self.FlattenData(state.GetDeviceData(domain, {}), domain)
      data.update(flat_data)
    hwid = state.GetDeviceData(self.KEY_HWID,
                               self.dut.CallOutput('crossystem hwid'))
    if hwid:
      data[self.KEY_HWID] = hwid
    return data

  def UpdateAutoResults(self, method, result, args):
    """Updates auto values (based on method) to results."""
    auto_values = self.METHODS[method].auto_values
    for k, v in auto_values.iteritems():
      result[k.format(*args)] = v

  def UpdateDeviceData(self, data):
    """Updates system device data according to the given data."""
    prefixes = [self.DOMAIN_SERIALS, self.DOMAIN_VPD, self.DOMAIN_COMPONENT,
                self.DOMAIN_FACTORY, self.KEY_HWID]
    illegal_keys = [k for k in data if k.partition('.')[0] not in prefixes]
    if illegal_keys:
      raise ValueError('Invalid response keys: %r' % illegal_keys)
    keys_to_delete = [k for k, v in data.iteritems() if v is None]
    state.DeleteDeviceData(keys_to_delete)
    data = dict((k, v) for k, v in data.iteritems() if k not in keys_to_delete)
    state.UpdateDeviceData(data)

  @staticmethod
  def FilterDict(data):
    """Returns a dict with privacy data filtered."""
    result = shelve_utils.DictShelfView(shelve_utils.InMemoryShelf())
    for k, v in data.iteritems():
      result.SetValue(k, v)
    if not result.GetKeys():
      return {}
    return privacy.FilterDict(result.GetValue(''))

  def _runTest(self):
    self.ui.AddEventHandler('retry', lambda unused_event: self.event.set())
    if self.args.server_url:
      server_proxy = xmlrpclib.ServerProxy(self.args.server_url,
                                           allow_none=True)
    else:
      server_proxy = shopfloor.get_instance(detect=True)

    if self.args.method not in self.METHODS:
      raise ValueError('Unknown method for shopfloor service: %s' %
                       self.args.method)

    # Prepare arguments
    method = self.args.method
    args = list(self.args.args or ())
    spec = self.METHODS[method]
    if spec.data_args:
      args = [state.GetDeviceData(k) for k in spec.data_args] + args
    if spec.has_data:
      args.insert(0, self.GetFactoryDeviceData())

    log_args = '(...)' if spec.has_privacy_args else tuple(args)

    logging.info('shopfloor_service: invoking %s%r', method, log_args)
    invocation_message = pprint.pformat({method: args})

    while not self.done:
      def ShowMessage(caption, css, message, retry=False):
        retry_button = ('<button onclick="test.sendTestEvent(\'retry\')">' +
                        i18n_test_ui.MakeI18nLabel('Retry') + '</button>'
                        if retry else '')
        self.template.SetState(
            i18n_test_ui.MakeI18nLabelWithClass(caption, css) +
            '<p><textarea rows=25 cols=90 readonly>' +
            test_ui.Escape(message, False) + '</textarea><p>' +
            retry_button)

      ShowMessage('Invoking shopfloor service', 'test-status-active large',
                  invocation_message)

      def HandleError(trace):
        ShowMessage('Shop floor exception:', 'test-status-failed large',
                    '\n'.join((trace.splitlines()[-1], invocation_message,
                               trace)), True)
        process_utils.WaitEvent(self.event)
        self.event.clear()

      try:
        result = getattr(server_proxy, method)(*args)
        logging.info('shopfloor_service: %r%r => %r',
                     method, log_args, self.FilterDict(result))
        self.UpdateAutoResults(method, result, args)
        self.UpdateDeviceData(result)
        self.done = True
      except xmlrpclib.Fault as f:
        logging.exception('Server fault occurred.')
        HandleError(f.faultString)
      except Exception:
        logging.exception('Exception invoking shopfloor service.')
        exception_str = debug_utils.FormatExceptionOnly()
        HandleError(exception_str)
        continue
