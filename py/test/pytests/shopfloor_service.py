# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Invoke remote procedure call for interaction with shopfloor backend.

Description
-----------
The Chromium OS Factory Software has defined a protocol, "Chrome OS Factory
Shopfloor Service Specification", to access factory manufacturing line shopfloor
system (or MES) backend system. This test allows interaction with a server
following the protocol.

For more information about Chrome OS Factory Shopfloor Service Specification,
read
https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/shopfloor/README.md

By default, the protocol has been simplified so you don't need to manually
generate or process ``FactoryDeviceData`` or ``DeviceData`` - just provide
the constant arguments from test list.

For example, the method ``NotifyStart(data, station)`` can be invoked by
(assume station is ``'SMT'``) ``method='NotifyStart'`` and ``args=['SMT']``.
Also the return value is automatically merged into Device Data (see
``cros.factory.test.device_data`` for more details).

For OEM Chromebook projects, you should only use the standard methods defined in
Chrome OS Factory Shopfloor Service Specification. However, if you need to work
on a customized project or using a fixture with XMLRPC interface, it is possible
to use this test by setting argument ``raw_invocation`` to True.

When ``raw_invocation`` is True, the invocation will simply run with argument
``args`` and ``kargs``, no auto-generation of FactoryDeviceData or DeviceData.
The return value will still be merged to device data.

Test Procedure
--------------
This is an automated test without user interaction unless manually 'retry' is
needed.

When started, the test will connect to remote server and try to invoke specified
method with given arguments, and will display return (error) messages and wait
for retry on failure.

Dependency
----------
No special dependency on client side, but the server must be implemented with
needed XMLRPC methods.

Examples
--------
To start 'SMT' station tests, add this in test list::

  {
    "pytest_name": "shopfloor_service",
    "args": {
      "args": ["SMT"],
      "method": "NotifyStart"
    }
  }

To invoke a non-standard call 'DoSomething' with args (1, 2) and keyword args
{'arg1': 1}::

  {
    "pytest_name": "shopfloor_service",
    "args": {
      "args": [1, 2],
      "raw_invocation": true,
      "kargs": {
        "arg1": 1
      },
      "method": "DoSomething"
    }
  }
"""


import collections.abc
import logging
import pprint
import threading

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.i18n import _
from cros.factory.test.rules import privacy
from cros.factory.test import server_proxy
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import log_utils
from cros.factory.utils import process_utils
from cros.factory.utils import shelve_utils
from cros.factory.utils import webservice_utils


class ServiceSpec:
  """The specification of shopfloor service API."""

  def __init__(self, has_data=True, auto_values=None, data_args=None,
               has_privacy_args=False):
    self.has_data = has_data
    self.has_privacy_args = has_privacy_args
    self.auto_values = auto_values or {}
    self.data_args = data_args


class ShopfloorService(test_case.TestCase):
  """Execution of remote shoploor service."""

  ARGS = [
      Arg('method', str,
          'Name of shopfloor service method to call'),
      Arg('args', list, 'Arguments for specified method.', default=None),
      Arg('kargs', collections.abc.Mapping, 'Keyword arguments for method.',
          default=None),
      Arg('raw_invocation', bool, 'Allow invocation of arbitrary calls.',
          default=False),
      Arg('server_url', str,
          'The URL to shopfloor service server', default=None),
  ]

  # The expected value for GetVersion, to help checking server implementation.
  SERVICE_VERSION = '1.0'

  # Domain of values to exchange.
  DOMAIN_SERIALS = device_data.KEY_SERIALS
  DOMAIN_FACTORY = device_data.KEY_FACTORY
  DOMAIN_VPD = device_data.KEY_VPD
  DOMAIN_COMPONENT = device_data.KEY_COMPONENT
  KEY_HWID = device_data.KEY_HWID

  KEY_VPD_USER_ECHO = device_data.KEY_VPD_USER_REGCODE
  KEY_VPD_GROUP_ECHO = device_data.KEY_VPD_GROUP_REGCODE

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
    self.dut = device_utils.CreateDUTInterface()
    self.event = threading.Event()
    self.ui.ToggleTemplateClass('font-large', True)

  def GetFactoryDeviceData(self):
    """Returns a dictionary in FactoryDeviceData format."""
    data = {}
    # Warning: DO NOT ADD ANY EXTRA DOMAINS HERE WITHOUT REVIEW.
    # Any protocol here must be compliant to Chrome OS Factory Shopfloor Service
    # Specification:
    # https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/shopfloor/README.md
    # Extra fields may cause security or privacy concern, and fail other
    # partners sharing same factory branch. Especially that DOMAIN_VPD cannot be
    # added since that would break privacy concern by registration (ECHO) codes.
    for domain in [self.DOMAIN_SERIALS, self.DOMAIN_FACTORY]:
      flat_data = device_data.FlattenData(
          device_data.GetDeviceData(domain, {}), domain)
      data.update(flat_data)
    hwid = device_data.GetDeviceData(self.KEY_HWID,
                                     self.dut.CallOutput('crossystem hwid'))
    if hwid:
      data[self.KEY_HWID] = hwid
    return data

  def UpdateAutoResults(self, method, result, args):
    """Updates auto values (based on method) to results."""
    auto_values = self.METHODS[method].auto_values
    for k, v in auto_values.items():
      result[k.format(*args)] = v

  def UpdateDeviceData(self, data):
    """Updates system device data according to the given data."""
    prefixes = [self.DOMAIN_SERIALS, self.DOMAIN_VPD, self.DOMAIN_COMPONENT,
                self.DOMAIN_FACTORY, self.KEY_HWID]
    illegal_keys = [k for k in data if k.partition('.')[0] not in prefixes]
    if illegal_keys:
      raise ValueError('Invalid response keys: %r' % illegal_keys)
    keys_to_delete = [k for k, v in data.items() if v is None]
    device_data.DeleteDeviceData(keys_to_delete)
    data = {k: v for k, v in data.items() if k not in keys_to_delete}
    device_data.UpdateDeviceData(data)

  @staticmethod
  def FilterDict(data):
    """Returns a dict with privacy data filtered."""
    result = shelve_utils.DictShelfView(shelve_utils.InMemoryShelf())
    for k, v in data.items():
      result.SetValue(k, v)
    if not result.GetKeys():
      return {}
    return privacy.FilterDict(result.GetValue(''))

  def runTest(self):
    self.event_loop.AddEventHandler(
        'retry', lambda unused_event: self.event.set())
    if self.args.server_url:
      server = webservice_utils.CreateWebServiceProxy(self.args.server_url)
    else:
      server = server_proxy.GetServerProxy()
      if self.args.raw_invocation:
        raise ValueError('Argument `raw_invocation` allowed only for external '
                         'server (need `server_url`).')

    # Prepare arguments
    method = self.args.method
    args = list(self.args.args or ())
    kargs = dict(self.args.kargs or {})

    if self.args.raw_invocation:
      spec = ServiceSpec(has_data=False)
    else:
      if self.args.kargs:
        raise ValueError('`kargs` only allowed for `raw_invocation`.')
      spec = self.METHODS.get(method)
      if not spec:
        raise ValueError('Unknown method for shopfloor service: %s' % method)

    if spec.data_args:
      args = [device_data.GetDeviceData(k) for k in spec.data_args] + args
    if spec.has_data:
      args.insert(0, self.GetFactoryDeviceData())

    log_args = '(...)' if spec.has_privacy_args else repr(tuple(args))
    log_args += repr(kargs) if kargs else ''

    logging.info('shopfloor_service: invoking %s%s', method, log_args)
    invocation_message = pprint.pformat({method: args}) + (
        pprint.pformat(kargs) if kargs else '')

    # Reduce messages.
    logger = log_utils.NoisyLogger(
        lambda fault, prompt: logging.exception(prompt, fault))

    while True:
      def ShowMessage(caption, css, message, retry=False):
        retry_button = [
            '<button data-test-event="retry">',
            _('Retry'), '</button>'
        ] if retry else ''
        self.ui.SetState([
            '<span class="%s">' % css, caption,
            '</span><p><textarea rows=25 cols=90 readonly>',
            test_ui.Escape(message, False), '</textarea><p>', retry_button
        ])

      ShowMessage(_('Invoking shopfloor service'), 'test-status-active large',
                  invocation_message)

      def HandleError(message):
        ShowMessage(_('Shopfloor exception:'), 'test-status-failed large',
                    '\n'.join((message.splitlines()[-1],
                               invocation_message, message)), True)
        process_utils.WaitEvent(self.event)
        self.event.clear()

      try:
        result = getattr(server, method)(*args, **kargs)
        logging.info('shopfloor_service: %s%s => %r',
                     method, log_args, self.FilterDict(result))
        self.UpdateAutoResults(method, result, args)
        self.UpdateDeviceData(result)
        break
      except server_proxy.Fault as f:
        message = f.faultString
        logger.Log(message, 'Server fault occurred: %s')
        HandleError(message)
      except Exception:
        message = debug_utils.FormatExceptionOnly()
        logger.Log(message, 'Exception invoking shopfloor service: %s')
        HandleError(message)
