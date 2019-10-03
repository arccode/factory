# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to ensure the power type and status of device under test.

Description
-----------
The test detects the power type of the underlying device. It is also used to
ask operator to unplug the AC from the device.

Test Procedure
--------------
To test if plugged AC power is detected properly:

1. Plug the designated power source to the device, and unplug all the other
   power sources.
2. Starts the test.

To test AC power unplugged:

1. Starts the test.
2. Follow the instruction on the UI to unplug the power.

Dependency
----------
- Need a power source.

For plugged with required power range:
- Need a USB PD power source with required power range.

Examples
--------
To test AC unplugged, add this to test list::

  {
    "pytest_name": "ac_power",
    "args": {
      "online": false
    }
  }

To test USBPD 45W plugged on usbpd port 0::

  {
    "pytest_name": "ac_power",
    "args": {
      "power_type": "USB_PD",
      "usbpd_power_range": [0, 45, 45],
      "online": true
    }
  }
"""

import numbers

from cros.factory.device import device_utils
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg

_PROBE_TIMES_ID = 'probed_times'
_AC_STATUS_ID = 'ac_status'
_AC_POWER_ID = 'ac_power'
_AC_TYPE_USB_PD = 'USB_PD'


class ACPowerTest(test_case.TestCase):
  """A test to instruct the operator to plug/unplug AC power.

  Args:
    power_type: The type of the power. None to skip power type check.
    usbpd_power_range: The required usbpd power range (min, max). None to skip
        power range check.
    online: True if expecting AC power. Otherwise, False.
    bft_fixture: If assigned, it commands the BFT fixture to
        plug/unplug an AC adapter.
    retries: Maximum number of retries allowed to pass the test.
    polling_period_secs: Polling period in seconds.
    silent_warning: Skips first N charger type mismatch before giving a
        warning.
  """

  ARGS = [
      Arg('power_type', str, 'Type of the power source', default=None),
      Arg('usbpd_power_range', list,
          'The required power usbpd power range [usbpd_port, min, max]',
          default=None),
      Arg('online', bool, 'True if expecting AC power', default=True),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, default=None),
      Arg('retries', int,
          'Maximum number of retries allowed to pass the test. '
          '0 means only probe once. Default None means probe forever.',
          default=None),
      Arg('polling_period_secs', numbers.Real,
          'Polling period in seconds.', default=1),
      Arg('silent_warning', int,
          'Skips first N charger type mismatch before giving a warning. '
          'Because EC needs about 1.6 seconds to identify charger type after '
          'it is plugged in, it skips first N mismatched probe.',
          default=2),
  ]

  def setUp(self):
    self._power = device_utils.CreateDUTInterface().power

    if not self.args.online:
      instruction = _('Unplug the charger.')
    elif self.args.power_type:
      instruction = _('Plug in the charger ({type})', type=self.args.power_type)
    else:
      instruction = _('Plug in the charger')

    self.ui.SetInstruction(instruction)

    self.ui.SetState(
        '<div id="%s"></div><div id="%s"></div><div id="%s"></div>' %
        (_PROBE_TIMES_ID, _AC_STATUS_ID, _AC_POWER_ID))

    self._power_state = {}
    self._last_type = None
    self._last_ac_present = None
    self._skip_warning_remains = self.args.silent_warning
    if self.args.usbpd_power_range is not None:
      testlog.UpdateParam(
          name='usbpd_power',
          description='Detected usbpd power.',
          value_unit='mW')

    # Prepare fixture auto test if needed.
    self.fixture = None
    if self.args.bft_fixture:
      self.fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

  def UpdateACPower(self, watt, min_watt, max_watt):
    self.ui.SetHTML(
        _('Detected power {watt} W, '
          'required power range ({min_watt} W, {max_watt} W)',
          watt=watt,
          min_watt=min_watt,
          max_watt=max_watt),
        id=_AC_POWER_ID)

  def UpdateACStatus(self, status):
    self.ui.SetHTML(status, id=_AC_STATUS_ID)

  def UpdateProbeTimes(self, num_probes):
    self.ui.SetHTML(
        _('Probed {times} / {total}', times=num_probes,
          total=self.args.retries),
        id=_PROBE_TIMES_ID)

  def CheckCondition(self):
    ac_present = self._power.CheckACPresent()
    current_type = self._power.GetACType()

    # Reset silent warning countdown when AC present status change.
    # Also reset _last_type as we want to give a warning for each
    # mismatched charger attached.
    if self._last_ac_present != ac_present:
      self._last_ac_present = ac_present
      self._skip_warning_remains = self.args.silent_warning
      self._last_type = None

    if ac_present != self.args.online:
      if not ac_present:
        self.UpdateACStatus(_('No AC adapter'))
      return False

    if self.args.power_type and self.args.power_type != current_type:
      if self._skip_warning_remains > 0:
        self.UpdateACStatus(_('Identifying AC adapter...'))
        self._skip_warning_remains -= 1
      elif self._last_type != current_type:
        self.UpdateACStatus(_('AC adapter type: {type}', type=current_type))
        session.console.warning(
            'Expecting %s but see %s', self.args.power_type, current_type)
        self._last_type = current_type
      return False

    if self.args.usbpd_power_range and self.args.power_type == _AC_TYPE_USB_PD:
      usbpd_power_infos = self._power.GetUSBPDPowerInfo()
      port, power_min, power_max = self.args.usbpd_power_range
      # USBPortInfo: (id, state, voltage (mV), current (mA))
      for info in usbpd_power_infos:
        if info.id != port:
          continue
        power_watt = info.voltage * info.current // 1000000
        self.UpdateACPower(power_watt, power_min, power_max)
        result = testlog.CheckNumericParam(
            'usbpdpower', power_watt, min=power_min, max=power_max)
        if not result:
          session.console.warning(
              'Expecting (%s, %s) watt usbpd power but see %s' %
              (power_min, power_max, power_watt))
        return result
      return False
    return True

  def runTest(self):
    if self.fixture:
      self.fixture.SetDeviceEngaged(bft_fixture.BFTFixture.Device.AC_ADAPTER,
                                    self.args.online)
    num_probes = 0

    while True:
      if self.args.retries is not None:
        self.UpdateProbeTimes(num_probes)
      if self.CheckCondition():
        break
      num_probes += 1
      if self.args.retries is not None and num_probes > self.args.retries:
        self.FailTask('Failed after probing %d times' % num_probes)
      # Prevent busy polling.
      self.Sleep(self.args.polling_period_secs)
