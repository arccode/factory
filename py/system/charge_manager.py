# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common # pylint: disable=W0611
from cros.factory import system
from cros.factory.system.ec import EC
from cros.factory.system.power import Power
from cros.factory.test.utils import Enum

class ChargeManagerException(Exception):
  pass

class ChargeManager(object):
  '''Properties:

    state: The current state (an element of either ErrorState or
      EC.ChargeState).
  '''
  _power = Power()
  _ec = system.GetEC()

  ErrorState = Enum(['BATTERY_NOT_PRESENT', 'AC_UNPLUGGED', 'BATTERY_ERROR'])

  def __init__(self, min_charge_pct, max_charge_pct):
    '''Constructor.

    Args:
      min_charge_pct: The minimum level of charge. Battery charges when charge
                      level is lower than this value. This value must be between
                      0 and 100.
      max_charge_pct: The maximum level of charge. Battery discharges when
                      charge level is higher than this value. This value must be
                      between 0 and 100, and must be higher than min_charge_pct.
    '''
    assert min_charge_pct >= 0
    assert min_charge_pct <= 100
    assert max_charge_pct >= 0
    assert max_charge_pct <= 100
    assert max_charge_pct >= min_charge_pct

    self._min_charge_pct = min_charge_pct
    self._max_charge_pct = max_charge_pct
    self.state = None

  def _SetState(self, new_state):
    if self.state != new_state:
      self.state = new_state
      logging.info("Charger state: %s", self.state)

  def _StartCharging(self):
    self._SetState(EC.ChargeState.CHARGE)
    self._ec.SetChargeState(EC.ChargeState.CHARGE)

  def _StopCharging(self):
    self._SetState(EC.ChargeState.IDLE)
    self._ec.SetChargeState(EC.ChargeState.IDLE)

  def _ForceDischarge(self):
    self._SetState(EC.ChargeState.DISCHARGE)
    self._ec.SetChargeState(EC.ChargeState.DISCHARGE)

  def AdjustChargeState(self):
    '''Adjust charge state according to battery level.

    If current battery level is lower than min_charge_pct, this method starts
    battery charging. If it is higher than max_charge_pct, this method forces
    battery discharge. Otherwise, charger is set to idle mode and is neither
    charging nor discharging.
    This method never throw exception.'''
    try:
      if not self._power.CheckBatteryPresent():
        self._SetState(self.ErrorState.BATTERY_NOT_PRESENT)
        return
      if not self._power.CheckACPresent():
        self._SetState(self.ErrorState.AC_UNPLUGGED)
        return

      charge = self._power.GetChargePct()
      if charge is None:
        self._SetState(self.ErrorState.BATTERY_ERROR)
      elif charge < self._min_charge_pct:
        self._StartCharging()
      elif charge > self._max_charge_pct:
        self._ForceDischarge()
      else:
        self._StopCharging()
    except Exception as e:  # pylint: disable=W0703
      logging.error('Unable to set charge state: %s', e)
