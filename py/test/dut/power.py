#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import time

import numpy

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut.component import DUTComponent
from cros.factory.utils.type_utils import Enum


class PowerException(Exception):
  pass


class Power(DUTComponent):
  # Power source types
  PowerSource = Enum(['BATTERY', 'AC'])

  ChargeState = Enum(['CHARGE', 'IDLE', 'DISCHARGE'])
  """An enumeration of possible charge states.

  - ``CHARGE``: Charge the device as usual.
  - ``IDLE``: Do not charge the device, even if connected to mains.
  - ``DISCHARGE``: Force the device to discharge.
  """

  # Regular expression for parsing output.
  EC_BATTERY_RE = re.compile(r'^\s+Present current\s+(\d+)\s+mA$', re.MULTILINE)
  EC_BATTERY_CHARGING_RE = re.compile(r'^\s+Flags\s+.*\s+CHARGING.*$',
                                      re.MULTILINE)
  EC_CHARGER_RE = re.compile(r'^chg_current = (\d+)mA$', re.MULTILINE)
  BATTERY_DESIGN_CAPACITY_RE = re.compile(
      r'Design capacity:\s+([1-9]\d*)\s+mAh')

  _sys = '/sys'

  def __init__(self, dut):
    super(Power, self).__init__(dut)
    self._battery_path = None
    self._current_state = None

  def ReadOneLine(self, file_path):
    """Reads one stripped line from given file on DUT.

    Args:
      file_path: The file path on DUT.

    Returns:
      String for the first line of file contents.
    """
    # splitlines() does not work on empty string so we have to check.
    contents = self._dut.ReadFile(file_path)
    if contents:
      return contents.splitlines()[0].strip()
    return ''

  def FindPowerPath(self, power_source):
    """Find battery path in sysfs."""
    if power_source == self.PowerSource.BATTERY:
      for p in self._dut.Glob(self._dut.path.join(
          self._sys, 'class/power_supply/*/type')):
        if self.ReadOneLine(p) == 'Battery':
          return self._dut.path.dirname(p)
    else:
      ac_path = self._dut.path.join(self._sys, 'class/power_supply/%s/online')
      if self._dut.path.exists(ac_path % 'AC'):
        return self._dut.path.dirname(ac_path % 'AC')
      p = self._dut.Glob(ac_path % '*')
      if p:
        # Systems with multiple USB-C ports may have multiple power sources.
        # Since the end goal is to determine if the system is powered, let’s
        # just return the first powered AC path if there’s any; otherwise
        # return the first in the list.
        for path in p:
          if self.ReadOneLine(path) == '1':
            return self._dut.path.dirname(path)
        return self._dut.path.dirname(p[0])
    raise PowerException('Cannot find %s' % power_source)

  def CheckACPresent(self):
    """Check if AC power is present."""
    try:
      p = self.FindPowerPath(self.PowerSource.AC)
      return self.ReadOneLine(self._dut.path.join(p, 'online')) == '1'
    except (PowerException, IOError):
      return False

  def GetACType(self):
    """Get AC power type."""
    try:
      p = self.FindPowerPath(self.PowerSource.AC)
      return self.ReadOneLine(self._dut.path.join(p, 'type'))
    except (PowerException, IOError):
      return 'Unknown'

  def CheckBatteryPresent(self):
    """Check if battery is present and also set battery path."""
    try:
      self._battery_path = self.FindPowerPath(self.PowerSource.BATTERY)
      return True
    except PowerException:
      return False

  def GetBatteryAttribute(self, attribute_name):
    '''Get a battery attribute.

    Args:
      attribute_name: The name of attribute in sysfs.

    Returns:
      Content of the attribute in str.
    '''
    try:
      return self.ReadOneLine(self._dut.path.join(self._battery_path,
                                                  attribute_name))
    except IOError:
      # Battery driver is not fully initialized
      return None

  def GetCharge(self):
    """Get current charge level in mAh."""
    charge_now = self.GetBatteryAttribute('charge_now')
    if charge_now:
      return int(charge_now) / 1000
    else:
      return None

  def GetChargeMedian(self, read_count=10):
    """Read charge level several times and return the median."""
    charge_nows = []
    for _ in xrange(read_count):
      charge_now = self.GetCharge()
      if charge_now:
        charge_nows.append(charge_now)
      time.sleep(0.1)
    return numpy.median(charge_nows)

  def GetChargeFull(self):
    """Get full charge level in mAh."""
    charge_full = self.GetBatteryAttribute('charge_full')
    if charge_full:
      return int(charge_full) / 1000
    else:
      return None

  def GetChargePct(self, get_float=False):
    '''Get current charge level in percentage.

    Args:
      get_float: Returns charge percentage in float.

    Returns:
      Charge percentage in int/float.
    '''
    now = self.GetBatteryAttribute('charge_now')
    full = self.GetBatteryAttribute('charge_full')
    if now is None or full is None:
      now = self.GetBatteryAttribute('energy_now')
      full = self.GetBatteryAttribute('energy_full')
      if now is None or full is None:
        return None

    if float(full) <= 0:
      return None  # Something wrong with the battery
    charge_pct = float(now) * 100.0 / float(full)
    if get_float:
      return charge_pct
    else:
      return round(charge_pct)

  def GetWearPct(self):
    """Get current battery wear in percentage of new capacity."""
    capacity = self.GetBatteryAttribute('charge_full')
    design_capacity = self.GetBatteryAttribute('charge_full_design')

    if capacity is None or design_capacity is None:
      # No charge values, check for energy-reporting batteries
      capacity = self.GetBatteryAttribute('energy_full')
      design_capacity = self.GetBatteryAttribute('energy_full_design')
      if capacity is None or design_capacity is None:
        # Battery driver is not fully initialized
        return None

    if float(design_capacity) <= 0:
      return None  # Something wrong with the battery
    return 100 - (round(float(capacity) * 100 / float(design_capacity)))

  def SetChargeState(self, state):
    """Sets the charge state.

    Args:
      state: One of the three states in ChargeState.
    """
    try:
      if state == self.ChargeState.CHARGE:
        self._dut.CheckCall(['ectool', 'chargecontrol', 'normal'])
      elif state == self.ChargeState.IDLE:
        self._dut.CheckCall(['ectool', 'chargecontrol', 'idle'])
      elif state == self.ChargeState.DISCHARGE:
        self._dut.CheckCall(['ectool', 'chargecontrol', 'discharge'])
      else:
        raise self.Error('Unknown EC charge state: %s' % state)
    except Exception as e:
      raise self.Error('Unable to set charge state: %s' % e)

  def GetChargerCurrent(self):
    """Gets the amount of current we ask from charger.

    Returns:
      Interger value in mA.
    """
    re_object = self.EC_CHARGER_RE.findall(
        self._dut.CheckOutput(['ectool', 'chargestate', 'show']))
    if re_object:
      return int(re_object[0])
    else:
      raise self.Error('Cannot find current in ectool chargestate show')

  def GetBatteryCurrent(self):
    """Gets the amount of current battery is charging/discharging at.

    Returns:
      Integer value in mA.
    """
    ectool_output = self._dut.CheckOutput(['ectool', 'battery'])

    charging = bool(self.EC_BATTERY_CHARGING_RE.search(ectool_output))
    re_object = self.EC_BATTERY_RE.findall(ectool_output)
    if re_object:
      current = int(re_object[0])
    else:
      raise self.Error('Cannot find current in ectool battery output')
    return current if charging else -current

  def GetBatteryDesignCapacity(self):
    """Gets battery's design capacity.

    Returns:
      Battery's design capacity in mAh.

    Raises:
      DUTException if battery's design capacity cannot be obtained.
    """
    try:
      m = self.BATTERY_DESIGN_CAPACITY_RE.search(
          self._dut.CheckOutput(['ectool', 'battery']))
      if not m:
        raise self.Error('Design capacity not found.')
      return int(m.group(1))
    except Exception as e:
      raise self.Error('Unable to get battery design capacity: %s' % e)

  def GetPowerInfo(self):
    """Gets power information.

    Returns:
      The output of ectool powerinfo, like::

        AC Voltage: 5143 mV
        System Voltage: 11753 mV
        System Current: 1198 mA
        System Power: 14080 mW
        USB Device Type: 0x20010
        USB Current Limit: 2958 mA

      It can be further parsed by
      :py:func:`cros.factory.utils.string_utils.ParseDict` into a
      dict.

    Raises:
      DUTException if power information cannot be obtained.
    """
    return self._dut.CallOutput(['ectool', 'powerinfo'])

  def GetBatteryRegisters(self):
    """Gets battery registers on board.

    Returns:
      A dict with register offset as key and register value as value.
      Both key and value are integers.

    Raises:
      DUTException if any register is not available.
    """
    raise NotImplementedError
