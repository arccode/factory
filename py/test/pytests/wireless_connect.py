# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Connect to an AP.

Description
-----------
Connect to an AP.

Test Procedure
--------------
Auto.

Dependency
----------
- connection_manager goofy plugin

Examples
--------
To run this test on DUT, add a test item in the test list::

  {
    "pytest_name": "wireless_connect",
    "args": {
      "service_name": [
        {
          "ssid": "crosfactory20",
          "security": "psk",
          "passphrase": "crosfactory"
        },
        {
          "ssid": "crosfactory21",
          "security": "psk",
          "passphrase": "crosfactory"
        }
      ]
    }
  }
"""

from __future__ import division
from __future__ import print_function

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.goofy.plugins import plugin_controller
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg

class WirelessConnectTest(test_case.TestCase):
  """Basic wireless test class."""
  ARGS = [
      Arg('device_name', str,
          'The wifi interface',
          default=None),
      Arg('service_name', list,
          'A list of wlan config. See net_utils.WLAN for more information',
          default=[]),
      Arg('retries', int, 'Times to retry.',
          default=10),
      Arg('sleep_interval', int, 'Time to sleep.',
          default=3)]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._device_name = None
    self._connection_manager = plugin_controller.GetPluginRPCProxy(
        'connection_manager')

  def runTest(self):
    self._device_name = self._dut.wifi.SelectInterface(self.args.device_name)
    session.console.info('Selected device_name is %s.', self._device_name)
    services = self.args.service_name
    session.console.info('service = %r', services)
    if not self._connection_manager:
      self.FailTask('No connection_manager exists.')
    self._connection_manager.Reconnect(services)
    SSID_RE = re.compile('SSID: (.*)$', re.MULTILINE)
    ssid_list = [service.get('ssid') for service in services]
    for _ in range(self.args.retries):
      result = self._dut.CheckOutput(['iw', 'dev', self._device_name, 'link'])
      match = SSID_RE.search(result)
      if match and match.group(1) in ssid_list:
        self.PassTask()
      self.Sleep(self.args.sleep_interval)
    self.FailTask('Reach maximum retries.')
