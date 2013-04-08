#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
import re

from cros.factory.board.chromeos_board import ChromeOSBoard
from cros.factory.system.board import Board, BoardException
from cros.factory.system.power import Power, PowerException

class SpringPower(Power):
  """Power interface for spring board."""
  def __init__(self, board):
    super(SpringPower, self).__init__()
    self._board = board

  def CheckACPresent(self):
    """Returns the presence of AC.
    AC is present if
    1. AC Voltage > 4000 mV
    AND
    2. USB Device Type & 0x480 = 0."""
    # pylint: disable=W0212
    powerinfo_output = self._board._CallECTool(['powerinfo'])
    obj_ac = re.search('AC Voltage: (\d+) mV', powerinfo_output)
    obj_type = re.search('USB Device Type: (0x\d+)', powerinfo_output)
    if obj_ac:
      ac_voltage = obj_ac.group(1)
    else:
      raise PowerException('Can not get AC voltage.')
    if obj_type:
      device_type = obj_type.group(1)
    else:
      raise PowerException('Can not get USB device type.')

    return int(ac_voltage) > 4000 and (int(device_type, 16) & 0x480 == 0)

class SpringBoard(ChromeOSBoard):
  """Board interface for Spring."""
  def __init__(self):
    super(SpringBoard, self).__init__()
    self.power = SpringPower(self)

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
