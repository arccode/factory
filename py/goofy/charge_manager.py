# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

import factory_common # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn
from cros.factory.test import utils

class ChargeManagerException(Exception):
  pass

class ChargeManager(object):
  # Placed here so that we can mock them when unit testing.
  _Spawn = staticmethod(Spawn)
  _sys = "/sys"

  # Charger option bytes
  CHARGER_OPTION_NORMAL = "0xf912"
  CHARGER_OPTION_DISCHARGE = "0xf952"

  # Power source types
  PowerSource = utils.Enum(['BATTERY', 'MAINS'])

  def __init__(self, min_charge_pct, max_charge_pct):
    '''Constructor.

    Args:
      min_charge_pct: The minimum level of charge. Battery charges when charge
                      level is lower than this value. This value must be between
                      0 and 100.
      max_charge_pct: The maximum level of charge. Battery discharges when charge
                      level is higher than this value. This value must be
                      between 0 and 100, and must be higher than min_charge_pct.
    '''
    assert min_charge_pct >= 0
    assert min_charge_pct <= 100
    assert max_charge_pct >= 0
    assert max_charge_pct <= 100
    assert max_charge_pct >= min_charge_pct

    self._min_charge_pct = min_charge_pct
    self._max_charge_pct = max_charge_pct
    self._battery_path = None
    self._current_state = None

  def _ReadLine(self, path):
    with open(path, 'r') as f:
      return f.readline().strip()

  def _FindPowerPath(self, power_source):
    '''Find battery path in sysfs.'''
    if power_source == self.PowerSource.BATTERY:
      power_type = 'Battery'
    else:
      power_type = 'Mains'
    for p in glob.glob(os.path.join(self._sys, "class/power_supply/*/type")):
      if self._ReadLine(p) == power_type:
        return os.path.dirname(p)
    raise ChargeManagerException("Cannot find %s" % power_type)

  def _CheckACPresent(self):
    '''Check if AC power is present.'''
    try:
      self._FindPowerPath(self.PowerSource.MAINS)
      return True
    except ChargeManagerException:
      return False

  def _CheckBatteryPresent(self):
    '''Check if battery is present and also set battery path.'''
    try:
      self._battery_path = self._FindPowerPath(self.PowerSource.BATTERY)
      return True
    except ChargeManagerException:
      return False

  def _GetChargePct(self):
    '''Get current charge level in percentage.'''
    charge_now = self._ReadLine(self._battery_path + '/charge_now')
    charge_full = self._ReadLine(self._battery_path + '/charge_full')

    if float(charge_full) <= 0:
      return None # Something wrong with the battery
    return round(float(charge_now) * 100.0 / float(charge_full))

  def _SetChargerState(self, charger_option, force_idle):
    '''Set charger mode.

    Args:
      charger_option: 16-bit Charger option word:
                        CHARGER_OPTION_NORMAL: Normal operation.
                        CHARGER_OPTION_DISCHARGE: Force discharge.
      force_idle: "1" if force charge state machine idle. Otherwise, "0".
    '''
    self._Spawn(["ectool", "chargeforceidle", force_idle], ignore_stdout=True,
                log_stderr_on_error=True)
    self._Spawn(["ectool", "i2cwrite", "16", "0", "0x12", "0x12",
                charger_option], ignore_stdout=True, log_stderr_on_error=True)

  def _LogState(self, new_state):
    if self._current_state != new_state:
      self._current_state = new_state
      logging.info("Charger state: %s", new_state)

  def _StartCharging(self):
    self._LogState("charging")
    self._SetChargerState(self.CHARGER_OPTION_NORMAL, "0")

  def _StopCharging(self):
    self._LogState("idle")
    self._SetChargerState(self.CHARGER_OPTION_NORMAL, "1")

  def _ForceDischarge(self):
    self._LogState("discharging")
    self._SetChargerState(self.CHARGER_OPTION_DISCHARGE, "1")

  def AdjustChargeState(self):
    """Adjust charge state according to battery level.

    If current battery level is lower than min_charge_pct, this method starts
    battery charging. If it is higher than max_charge_pct, this method forces
    battery discharge. Otherwise, charger is set to idle mode and is neither
    charging nor discharging.
    This method never throw exception.
    """
    if not self._CheckBatteryPresent():
      self._LogState("Battery not present")
      return
    if not self._CheckACPresent():
      self._LogState("AC unplugged")
      return

    charge = self._GetChargePct()
    if charge is None:
      self._LogState("Battery error")
    elif charge < self._min_charge_pct:
      self._StartCharging()
    elif charge > self._max_charge_pct:
      self._ForceDischarge()
    else:
      self._StopCharging()
