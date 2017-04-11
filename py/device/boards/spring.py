#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.device import component
from cros.factory.device import power
from cros.factory.device.boards import chromeos


class SpringPower(power.Power):

  def SetChargeState(self, state):
    """Sets charge state for spring board.

    Args:
      state: Power.ChargeState.

    Raises:
      self.Error if state is unknown or it can not set charge state."""
    try:
      if state == self.ChargeState.CHARGE:
        self._dut.CheckCall(['ectool', 'extpwrcurrentlimit', '9999'])
        self._dut.CheckCall(['ectool', 'gpioset', 'charger_en', '1'])
      elif state == self.ChargeState.IDLE:
        self._dut.CheckCall(['ectool', 'extpwrcurrentlimit', '9999'])
        self._dut.CheckCall(['ectool', 'gpioset', 'charger_en', '0'])
      elif state == self.ChargeState.DISCHARGE:
        self._dut.CheckCall(['ectool', 'extpwrcurrentlimit', '0'])
        self._dut.CheckCall(['ectool', 'gpioset', 'charger_en', '0'])
      else:
        raise self.Error('Unknown EC charge state: %s' % state)
    except Exception as e:
      raise self.Error('Unable to set charge state: %s' % e)

  def GetChargerCurrent(self):
    """Charger current is not available on spring board."""
    raise NotImplementedError

  def GetPowerInfo(self):
    """Gets ectool powerinfo on spring board."""
    try:
      output = self._dut.CheckCall(['ectool', 'powerinfo'])
    except Exception as e:
      raise self.Error('Unable to get powerinfo: %s' % e)
    return output

  def GetBatteryRegisters(self):
    """Gets battery registers on spring board.

    Returns:
      A dict with register offset as key and register value as value.
      Both key and value are integers.

    Raises:
      self.Error if any register is not available.
    """
    regs = range(0, 0x1d) + range(0x20, 0x24) + [0x2f] + range(0x3c, 0x40)
    try:
      ret = dict((reg, self._dut.ec.I2CRead(0, 0x16, reg)) for reg in regs)
    except Exception as e:
      raise self.Error('Unable to get battery registers: %s' % e)
    return ret


class SpringBoard(chromeos.ChromeOSBoard):
  """Board interface for Spring."""

  @component.DeviceProperty
  def power(self):
    return SpringPower(self)
