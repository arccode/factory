#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
import logging

from cros.factory.board.chromeos_board import ChromeOSBoard
from cros.factory.system.board import Board, BoardException
from cros.factory.test import factory


class SnowBoard(ChromeOSBoard):
  """Board interface for Snow."""

  def GetTemperatures(self):
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
      return [int(f.readline().rstrip()) / 1000]

  def GetMainTemperatureIndex(self):
    return 0

  def GetTemperatureSensorNames(self):
    return ['CPU']

  def GetFanRPM(self):
    raise NotImplementedError

  def SetFanRPM(self, rpm):
    raise NotImplementedError

  def SetChargeState(self, state):
    try:
      if state == Board.ChargeState.CHARGE:
        self._CallECTool(['gpioset', 'charger_en', '1'])
        logging.info('Enabled the charger.')
      elif state == Board.ChargeState.IDLE:
        self._CallECTool(['gpioset', 'charger_en', '0'])
        logging.info('Disabled the charger.')
      elif state == Board.ChargeState.DISCHARGE:
        self._CallECTool(['gpioset', 'charger_en', '0'])
        factory.console.info('Can not force discharging.'
                             'Disabled the charger instead.'
                             'IF SYSTEM POWER IS OFF, PLEASE UNPLUG AC.')
      else:
        raise BoardException('Unknown SnowBoard charge state: %s' % state)
    except Exception as e:
      raise BoardException('Unable to set charge state in SnowBoard: %s' % e)

  def GetChargerCurrent(self):
    """Charger current is not available on snow board."""
    raise NotImplementedError
