#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.board.chromeos_board import ChromeOSBoard
from cros.factory.system.board import Board, BoardException

class SpringBoard(ChromeOSBoard):
  """Board interface for Spring."""
  def __init__(self):
    super(SpringBoard, self).__init__()

  def GetTemperatures(self):
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
      return [int(f.readline().rstrip())/1000]

  def GetMainTemperatureIndex(self):
    return 0

  def GetTemperatureSensorNames(self):
    return ['CPU']

  def GetFanRPM(self):
    raise NotImplementedError

  def SetFanRPM(self, rpm):
    raise NotImplementedError

  def SetChargeState(self, state):
    """Sets charge state for spring board.

    Args:
      state: Board.ChargeState.

    Raises:
      BoardException if state is unknown or it can not set charge state."""
    try:
      if state == Board.ChargeState.CHARGE:
        self._CallECTool(['extpwrcurrentlimit', '9999'])
        self._CallECTool(['gpioset', 'charger_en', '1'])
      elif state == Board.ChargeState.IDLE:
        self._CallECTool(['extpwrcurrentlimit', '9999'])
        self._CallECTool(['gpioset', 'charger_en', '0'])
      elif state == Board.ChargeState.DISCHARGE:
        self._CallECTool(['extpwrcurrentlimit', '0'])
        self._CallECTool(['gpioset', 'charger_en', '0'])
      else:
        raise BoardException('Unknown EC charge state: %s' % state)
    except Exception as e:
      raise BoardException('Unable to set charge state: %s' % e)

  def GetChargerCurrent(self):
    """Charger current is not available on spring board."""
    raise NotImplementedError
