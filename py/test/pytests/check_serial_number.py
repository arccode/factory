# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks if serial number is set correctly on a device.

Description
-----------
Some tests, for example, RF graphyte, assume DUTs have MLB serial number
available (in VPD and device data).  And the test will fail if a DUT
doesn't have MLB SN (e.g. it skipped previous station).

This test gets serial number from different sources and check if they are equal.

Test Procedure
--------------
This is an automated test.  It requires user interaction only if the test
failed, or if the "manual_check" flag is turned on.  This test will,

1. try to connect to device's state server
2. the device must have device_id
3. get SN from state server
4. get SN from VPD
5. these two SN must match

Dependency
----------

1. SSH connection (if we are checking remote device)
2. DUT is running factory software

Examples
--------
This test is already defined as "CheckSerialNumber"
in `generic_common.test_list.json` and "StationCheckSerialNumber" in
`station_based.test_list.json`. This test is turned on by default in station
based test list. You can disable it by setting `constants.check_serial_number`
to `false`::

  {
    "constants": {
      "check_serial_number": false
    }
  }

By default, this pytest checks mlb_serial_number. If you want to check serial
number instead::

  {
    "pytest_name": "check_serial_number",
    "args": {
      "sn_name": "serial_number"
    }
  }

By default, this pytest passes if the serial numbers match. If you want
additional manual confirmation (e.g. also match the serial number printed on
the device)::

  {
    "pytest_name": "check_serial_number",
    "args": {
      "manual_check": true
    }
  }

"""

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


HTML = """
<div style="font-size:2em">
  <div>
    Device Data: <span id='device-data-value'></span>
  <div>
  <div>
    VPD: <span id='vpd-value'></span>
  <div>
  <div id='pass_message' style='color:green'></div>
  <div id='fail_message' style='color:red'></div>
</div>
"""


class CheckDeviceState(test_case.TestCase):
  ARGS = [
      Arg('sn_name', str,
          'name of the serial number, e.g. "serial_number" or '
          '"mlb_serial_number"',
          default='mlb_serial_number'),
      Arg('manual_check', bool,
          'If set to true, this test needs operator to press ENTER or ESC to '
          'pass or fail the test case.',
          default=False)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.SetTitle(_('Checking Device State'))

  def runTest(self):
    sn_name = self.args.sn_name

    self.ui.SetState(HTML)

    success = True

    if self.dut.link.IsLocal():
      proxy = state.GetInstance()
    else:
      proxy = state.GetInstance(self.dut.link.host)

    # must have device_id
    if not self.dut.info.device_id:
      self.ui.SetHTML('No device_id<br />', id='fail_message', append=True)
      success = False

    device_data_sn = proxy.DataShelfGetValue(
        key='device.serials.%s' % sn_name, optional=True)
    self.ui.SetHTML(str(device_data_sn), id='device-data-value')
    vpd_sn = self.dut.CallOutput('vpd -g %s' % sn_name) or None
    self.ui.SetHTML(str(vpd_sn), id='vpd-value')

    if not device_data_sn:
      self.ui.SetHTML('%s not in device data<br />' % sn_name,
                      id='fail_message', append=True)
      success = False

    if not vpd_sn:
      self.ui.SetHTML('%s not in VPD<br />' % sn_name,
                      id='fail_message', append=True)
      success = False

    if vpd_sn != device_data_sn:
      self.ui.SetHTML(
          'Device data and VPD doesn\'t match<br />',
          id='fail_message', append=True)
      success = False

    if success:
      session.console.info('OK: %s=%s', sn_name, device_data_sn)
      if self.args.manual_check:
        self.ui.SetHTML(
            'Please press ENTER to pass or ESC to fail the test.<br />',
            id='pass_message', append=True)
        self.ui.BindStandardPassKeys()
        self.ui.BindStandardFailKeys()
        self.WaitTaskEnd()
    else:
      self.ui.SetHTML(
          'Failed, Press ENTER to continue<br />',
          id='message', append=True)
      self.ui.WaitKeysOnce(keys=[test_ui.ENTER_KEY])
      self.FailTask('Invalid device state (%s error)' % sn_name)
