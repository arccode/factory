# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verify and close modem access authority.

Description
-----------
This test verifies the modem access level. If the access level is not 0,
this test will try to set it to 0.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. Verify the access level of modem is 0. Pass the test if so.
2. Set the access level to 0.
3. Verify the access level of modem is 0. Pass the test if so.

Dependency
----------
- `modem`

Examples
--------
To verify and set modem access level to 0::

  {
    "pytest_name": "modem_security",
    "disable_services": ["modemmanager"]
  }
"""

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_case
from cros.factory.test.utils import serial_utils


MODEM_SERIAL_PORT = '/dev/ttyACM0'
ACCESS_LEVEL_RE = re.compile('^access_level = [0-9]', re.MULTILINE)


class ModemSecurity(test_case.TestCase):

  def setUp(self):
    self._serial_dev = serial_utils.SerialDevice(log=True)
    self._serial_dev.Connect(port=MODEM_SERIAL_PORT, timeout=1, writeTimeout=1)

  def tearDown(self):
    if self._serial_dev:
      self._serial_dev.Disconnect()

  def RunATCommand(self, command):
    response = self._serial_dev.SendReceive(command + '\r\n', size=0)
    if 'OK' not in response:
      self.FailTask('Bad response')
    return response

  def runTest(self):
    # Check whether access authority is closed already first.
    response = self.RunATCommand('AT@sec:status_info()')
    if ACCESS_LEVEL_RE.search(response).group(0) == 'access_level = 0':
      return

    # If access authority is still open then try to close it.
    self.RunATCommand('AT@sec:code_clear(0)')
    response = self.RunATCommand('AT@sec:status_info()')
    if ACCESS_LEVEL_RE.search(response).group(0) != 'access_level = 0':
      # If we can't close the access authority then raise this failure.
      self.FailTask('Failed to set the access_level')
