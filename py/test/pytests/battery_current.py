# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test battery charging/discharging current.

Description
-----------
Test battery charging and discharging current.

If `usbpd_info` is set, also prompt operator to insert a power adapter of given
voltage to the given USB type C port.

The `usbpd_info` is a sequence `(usbpd_port, min_millivolt, max_millivolt)`,
represent the USB type C port to insert power adapter:

- ``usbpd_port``: (int) usbpd_port number. Specify which port to insert power
  line.
- ``min_millivolt``: (int) The minimum millivolt the power must provide.
- ``max_millivolt``: (int) The maximum millivolt the power must provide.

Test Procedure
--------------
1. If `max_battery_level` is set, check that initial battery level is lower
   than the value.
2. If `usbpd_info` is set, prompt the operator to insert a power adapter of
   given voltage to the given USB type C port, and pass this step when one is
   detected.
3. If `min_charging_current` is set, force the power into charging mode, and
   check if the charging current is larger than the value.
4. If `min_discharging_current` is set, force the power into discharging mode,
   and check if the discharging current is larger than the value.
5. If `current_difference` is set, force the power into charging mode first,
   and record the charging current. Then force the power into discharging mode,
   and also record the discharging current. Pass the test if the (average
   charging current - average discharging current) is greater or equal to the
   value.

Each step would fail after `timeout_secs` seconds.

Dependency
----------
Device API cros.factory.device.power.

If `usbpd_info` is set, device API cros.factory.device.usb_c.GetPDPowerStatus
is also used.

Examples
--------
To check battery can charge and discharge, add this in test list::

  {
    "pytest_name": "battery_current",
    "args": {
      "min_charging_current": 250,
      "min_discharging_current": 400
    }
  }

Sometimes, the system consumes more power than the charger. In that case, we
could set the min_charging_current to negative value, and the test would pass
if the battery discharges less than 150 mA. See b/183679223#comment25::

  {
    "pytest_name": "battery_current",
    "args": {
      "min_charging_current": -150,
      "min_discharging_current": 400
    }
  }

Alternatively, we could also set::

  {
    "pytest_name": "battery_current",
    "args": {
      "current_difference": 250
    }
  }

To check that a 15V USB type C power adapter is connected to port 0, add this
in test list::

  {
    "pytest_name": "battery_current",
    "args": {
      "usbpd_info": [0, 14500, 15500],
      "usbpd_prompt": "i18n! USB TypeC"
    }
  }
"""

import logging

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils


def _GetPromptText(current, target):
  return _(
      'Waiting for {target_status} current to meet {target_current} mA.'
      ' (Currently {status} at {current} mA)',
      target_status=_('charging') if target >= 0 else _('discharging'),
      target_current=abs(target),
      status=_('charging') if current >= 0 else _('discharging'),
      current=abs(current))


class BatteryCurrentTest(test_case.TestCase):
  """A factory test to test battery charging/discharging current."""
  ARGS = [
      Arg('min_charging_current', int, 'minimum allowed charging current',
          default=None),
      Arg('min_discharging_current', int, 'minimum allowed discharging current',
          default=None),
      Arg(
          'current_difference', int,
          'The minimum current difference between the charging mode and'
          ' discharging mode.', default=None),
      Arg('retry_times', int, 'Retry for a number of times if the'
          ' current_difference test fails', default=2),
      Arg('timeout_secs', int, 'Test timeout value', default=30),
      Arg('max_battery_level', int, 'maximum allowed starting battery level',
          default=None),
      Arg(
          'usbpd_info', list,
          'A sequence [usbpd_port, min_millivolt, max_millivolt] used to '
          'select a particular port from a multi-port DUT.', default=None),
      Arg(
          'use_max_voltage', bool,
          'Use the negotiated max voltage in `ectool usbpdpower` to check '
          'charger voltage, in case that instant voltage is not supported.',
          default=False),
      i18n_arg_utils.I18nArg('usbpd_prompt',
                             'prompt operator which port to insert', default='')
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._power = self._dut.power
    if self.args.usbpd_info:
      self._CheckUSBPDInfoArg(self.args.usbpd_info)
      self._usbpd_port = self.args.usbpd_info[0]
      self._usbpd_min_millivolt = self.args.usbpd_info[1]
      self._usbpd_max_millivolt = self.args.usbpd_info[2]
    self._usbpd_prompt = self.args.usbpd_prompt

  def _CheckUSBPDInfoArg(self, info):
    if len(info) == 5:
      check_types = (int, str, str, int, int)
    elif len(info) == 3:
      check_types = (int, int, int)
    else:
      raise ValueError('ERROR: invalid usbpd_info item: ' + str(info))

    for i, (info_i, check_type) in enumerate(zip(info, check_types)):
      if not isinstance(info_i, check_type):
        logging.error('(%s)usbpd_info[%d] type is not %s', type(info_i), i,
                      check_type)
        raise ValueError('ERROR: invalid usbpd_info[%d]: ' % i + str(info))

  def _LogCurrent(self, current):
    if current >= 0:
      logging.info('Charging current = %d mA', current)
    else:
      logging.info('Discharging current = %d mA', -current)

  def _CheckUSBPD(self):
    for unused_i in range(10):
      status = self._dut.usb_c.GetPDPowerStatus()
      voltage_field = ('max_millivolt' if self.args.use_max_voltage else
                       'millivolt')
      if voltage_field not in status[self._usbpd_port]:
        self.ui.SetState(
            _('Insert power to {prompt}({voltage}mV)',
              prompt=self._usbpd_prompt,
              voltage=0))
        logging.info('No millivolt detected in port %d', self._usbpd_port)
        return False
      millivolt = status[self._usbpd_port][voltage_field]
      logging.info('millivolt %d, acceptable range (%d, %d)', millivolt,
                   self._usbpd_min_millivolt, self._usbpd_max_millivolt)
      self.ui.SetState(
          _('Insert power to {prompt}({voltage}mV)',
            prompt=self._usbpd_prompt,
            voltage=millivolt))
      if not (self._usbpd_min_millivolt <= millivolt <=
              self._usbpd_max_millivolt):
        return False
      self.Sleep(0.1)
    return True

  def _CheckCharge(self):
    current = self._power.GetBatteryCurrent()
    target = self.args.min_charging_current
    self._LogCurrent(current)
    self.ui.SetState(_GetPromptText(current, target))
    return current >= target

  def _CheckDischarge(self):
    current = self._power.GetBatteryCurrent()
    target = self.args.min_discharging_current
    self._LogCurrent(current)
    self.ui.SetState(_GetPromptText(current, -target))
    return -current >= target

  def _GetAverageCurrent(self, total_measure_secs=3, poll_interval_secs=0.2):
    """Average current for a given period of time."""
    times_to_count = int(total_measure_secs / poll_interval_secs)
    acc_current = 0
    for _ in range(times_to_count):
      acc_current += self._power.GetBatteryCurrent()
      self.Sleep(poll_interval_secs)

    return acc_current / times_to_count

  def _CheckCurrentDifference(self):
    target = self.args.current_difference

    self._power.SetChargeState(self._power.ChargeState.CHARGE)
    # It takes 1~2 seconds for the power state to change,
    # so sleeping for 3 seconds should be enough.
    self.Sleep(3)
    charging_current = self._GetAverageCurrent()
    logging.info('Average current in charging mode: %f', charging_current)

    self._power.SetChargeState(self._power.ChargeState.DISCHARGE)
    self.Sleep(3)
    discharging_current = self._GetAverageCurrent()
    logging.info('Average current in discharging mode: %f', discharging_current)
    present_difference = charging_current - discharging_current

    self.ui.SetState(
        _(
            'Average current in charging mode is {charging_current}<br>'
            'Average current in discharging mode is {discharging_current}<br>'
            'Target current difference is {target}, but present current'
            ' difference is {present_difference}',
            charging_current=charging_current,
            discharging_current=discharging_current, target=target,
            present_difference=present_difference))
    return present_difference >= target

  def _CheckCurrentDifferenceWithRetry(self):
    self.ui.SetState(
        _('Calculating the current difference between charging mode and'
          ' discharging mode.'))

    for times in range(self.args.retry_times + 1):
      if self._CheckCurrentDifference():
        break
      logging.info('CheckCurrentDifference failed. This is the %d try.',
                   times + 1)
      self.ui.SetState(
          _('CheckCurrentDifference failed. This is the {times} try',
            times=times + 1), append=True)
    else:
      self.FailTask('battery_current test failed.')

  def runTest(self):
    """Main entrance of charger test."""
    self.assertTrue(self._power.CheckBatteryPresent())
    if self.args.max_battery_level:
      self.assertLessEqual(self._power.GetChargePct(),
                           self.args.max_battery_level,
                           'Starting battery level too high')
    if self.args.usbpd_info is not None:
      sync_utils.PollForCondition(
          poll_method=self._CheckUSBPD, poll_interval_secs=0.5,
          condition_name='CheckUSBPD',
          timeout_secs=self.args.timeout_secs)
    if self.args.min_charging_current:
      self._power.SetChargeState(self._power.ChargeState.CHARGE)
      sync_utils.PollForCondition(
          poll_method=self._CheckCharge, poll_interval_secs=0.5,
          condition_name='ChargeCurrent',
          timeout_secs=self.args.timeout_secs)
    if self.args.min_discharging_current:
      self._power.SetChargeState(self._power.ChargeState.DISCHARGE)
      sync_utils.PollForCondition(poll_method=self._CheckDischarge,
                                  poll_interval_secs=0.5,
                                  condition_name='DischargeCurrent',
                                  timeout_secs=self.args.timeout_secs)
    if self.args.current_difference:
      self._CheckCurrentDifferenceWithRetry()

  def tearDown(self):
    # Must enable charger to charge or we will drain the battery!
    self._power.SetChargeState(self._power.ChargeState.CHARGE)
