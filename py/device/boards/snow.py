# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.device.boards import chromeos
from cros.factory.device import device_types
from cros.factory.device import power
from cros.factory.test import session


class SnowPower(power.Power):

  def SetChargeState(self, state):
    try:
      if state == self.ChargeState.CHARGE:
        self._device.CheckCall(['ectool', 'gpioset', 'charger_en', '1'])
        logging.info('Enabled the charger.')
      elif state == self.ChargeState.IDLE:
        self._device.CheckCall(['ectool', 'gpioset', 'charger_en', '0'])
        logging.info('Disabled the charger.')
      elif state == self.ChargeState.DISCHARGE:
        self._device.CheckCall(['ectool', 'gpioset', 'charger_en', '0'])
        session.console.info('Can not force discharging.'
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

  @device_types.DeviceProperty
  def power(self):
    return SnowPower(self)
