#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.dut import component
from cros.factory.test.dut import power
from cros.factory.test.dut import thermal
from cros.factory.test.dut.boards import chromeos


class SnowThermal(thermal.ECToolThermal):

  def GetTemperatures(self):
    raw = self._dut.ReadFile('/sys/class/thermal/thermal_zone0/temp')
    return [int(raw.splitlines()[0].rstrip()) / 1000]

  def GetMainTemperatureIndex(self):
    return 0

  def GetTemperatureSensorNames(self):
    return ['CPU']

  def GetFanRPM(self, fan_id=None):
    raise NotImplementedError

  def SetFanRPM(self, rpm, fan_id=None):
    raise NotImplementedError


class SnowPower(power.Power):

  def SetChargeState(self, state):
    try:
      if state == self.ChargeState.CHARGE:
        self._dut.CheckCall(['ectool', 'gpioset', 'charger_en', '1'])
        logging.info('Enabled the charger.')
      elif state == self.ChargeState.IDLE:
        self._dut.CheckCall(['ectool', 'gpioset', 'charger_en', '0'])
        logging.info('Disabled the charger.')
      elif state == self.ChargeState.DISCHARGE:
        self._dut.CheckCall(['ectool', 'gpioset', 'charger_en', '0'])
        factory.console.info('Can not force discharging.'
                             'Disabled the charger instead.'
                             'IF SYSTEM POWER IS OFF, PLEASE UNPLUG AC.')
      else:
        raise self.Error('Unknown SnowBoard charge state: %s' % state)
    except Exception as e:
      raise self.Error('Unable to set charge state in SnowBoard: %s' % e)

  def GetChargerCurrent(self):
    """Charger current is not available on snow board."""
    raise NotImplementedError


class SnowBoard(chromeos.ChromeOSBoard):
  """Board interface for Snow."""

  @component.DUTProperty
  def power(self):
    return SnowPower(self)

  @component.DUTProperty
  def thermal(self):
    return SnowThermal(self)

