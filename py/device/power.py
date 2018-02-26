# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import logging
import re
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types

from cros.factory.external import enum
from cros.factory.external import numpy


class PowerException(types.DeviceException):
  pass


class Power(types.DeviceComponent):

  # pylint: disable=no-init
  class PowerSource(enum.Enum):
    """Power source types"""
    BATTERY = 1
    AC = 2

  # pylint: disable=no-init
  class ChargeState(enum.Enum):
    """An enumeration of possible charge states.

    - ``CHARGE``: Charge the device as usual.
    - ``IDLE``: Do not charge the device, even if connected to mains.
    - ``DISCHARGE``: Force the device to discharge.
    """
    CHARGE = 'Charging'
    IDLE = 'Idle'
    DISCHARGE = 'Discharging'

  # Regular expression for parsing output.
  EC_CHARGER_RE = re.compile(r'^chg_current = (\d+)mA', re.MULTILINE)

  _sys = '/sys'

  def __init__(self, dut, pd_name=None):
    super(Power, self).__init__(dut)
    self._current_state = None
    self._pd_name = pd_name

  def ReadOneLine(self, file_path):
    """Reads one stripped line from given file on DUT.

    Args:
      file_path: The file path on DUT.

    Returns:
      String for the first line of file contents.
    """
    # splitlines() does not work on empty string so we have to check.
    contents = self._device.ReadSpecialFile(file_path)
    if contents:
      return contents.splitlines()[0].strip()
    return ''

  def FindPowerPath(self, power_source):
    """Find battery path in sysfs.

    Note few attributes, especially 'online', is usually implemented as cached
    value and only updated if we read some dynamic values (for example
    voltage_now) or a host event from EC is discovered. This implies if host
    events are broken, many values won't be updated - and this is critical for
    FindPowerPath.

    For devices in early stage, you probably want to extend FindPowerPath by
    reading voltage_now from all power_supply entries.
    """
    def GetValue(path, sub_path):
      full_path = self._device.path.join(path, sub_path)
      if not self._device.path.exists(full_path):
        return None
      return self.ReadOneLine(full_path)

    all_power_supplies = self._device.Glob(
        self._device.path.join(self._sys, 'class/power_supply/*'))

    if power_source == self.PowerSource.BATTERY:
      # Some HID peripherals, for example Stylus, may has its own battery and
      # appear in power_supply as well, with scope='Device'; and we do want to
      # skip them.
      power_supplies = [
          p for p in all_power_supplies if GetValue(p, 'type') == 'Battery' and
          GetValue(p, 'scope') != 'Device'
      ]
    else:
      power_supplies = [
          p for p in all_power_supplies if GetValue(p, 'type') != 'Battery'
      ]

    if power_supplies:
      # Systems with multiple USB-C ports may have multiple power sources.
      # Since the end goal is to determine if the system is powered, let's
      # just return the first powered AC path if there's any; otherwise
      # return the first in the list.
      for p in power_supplies:
        if GetValue(p, 'online') == '1':
          return p
      return power_supplies[0]

    raise PowerException('Cannot find %s' % power_source)

  def CheckACPresent(self):
    """Check if AC power is present."""
    try:
      p = self.FindPowerPath(self.PowerSource.AC)
      return self.ReadOneLine(self._device.path.join(p, 'online')) == '1'
    except (PowerException, IOError):
      return False

  def GetACType(self):
    """Get AC power type."""
    try:
      p = self.FindPowerPath(self.PowerSource.AC)
      return self.ReadOneLine(self._device.path.join(p, 'type'))
    except (PowerException, IOError):
      return 'Unknown'

  @types.DeviceProperty
  def _battery_path(self):
    """Get battery path.

    Use cached value if available.

    Returns:
      Battery path if available, None otherwise.
    """
    try:
      return self.FindPowerPath(self.PowerSource.BATTERY)
    except PowerException:
      return None

  def CheckBatteryPresent(self):
    """Check if battery is present."""
    return bool(self._battery_path)

  def GetBatteryAttribute(self, attribute_name):
    """Get a battery attribute.

    Args:
      attribute_name: The name of attribute in sysfs.

    Returns:
      Content of the attribute in str.
    """
    try:
      return self.ReadOneLine(
          self._device.path.join(self._battery_path, attribute_name))
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
    """Get current charge level in percentage.

    Args:
      get_float: Returns charge percentage in float.

    Returns:
      Charge percentage in int/float.
    """
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

  def GetChargeState(self):
    """Returns the charge state.

    Returns:
      One of the three states in ChargeState.
    """
    return self.ChargeState(self.GetBatteryAttribute('status')).value

  def SetChargeState(self, state):
    """Sets the charge state.

    Args:
      state: One of the three states in ChargeState.
    """
    try:
      if state == self.ChargeState.CHARGE:
        self._device.CheckCall(['ectool', 'chargecontrol', 'normal'])
      elif state == self.ChargeState.IDLE:
        self._device.CheckCall(['ectool', 'chargecontrol', 'idle'])
      elif state == self.ChargeState.DISCHARGE:
        self._device.CheckCall(['ectool', 'chargecontrol', 'discharge'])
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
        self._device.CheckOutput(['ectool', 'chargestate', 'show']))
    if re_object:
      return int(re_object[0])
    else:
      raise self.Error('Cannot find current in ectool chargestate show')

  def GetBatteryCurrent(self):
    """Gets the amount of current battery is charging/discharging at.

    Returns:
      Integer value in mA.
    """
    charging = (self.GetBatteryAttribute('status') == 'Charging')
    current = self.GetBatteryAttribute('current_now')
    if current is None:
      raise self.Error('Cannot find %s/current_now' % self._battery_path)
    current_ma = abs(int(current)) / 1000
    return current_ma if charging else -current_ma

  def GetBatteryDesignCapacity(self):
    """Gets battery's design capacity.

    Returns:
      Battery's design capacity in mAh.

    Raises:
      DeviceException if battery's design capacity cannot be obtained.
    """
    design_capacity = self.GetBatteryAttribute('charge_full_design')
    if design_capacity is None:
      raise self.Error('Design capacity not found.')
    try:
      return int(design_capacity) / 1000
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
      DeviceException if power information cannot be obtained.
    """
    return self._device.CallOutput(['ectool', 'powerinfo'])

  def GetUSBPDPowerInfo(self):
    """Gets USB PD power information.

    Returns:
      The output of ectool usbpdpower, like::

        Port 0: Disconnected
        Port 1: SNK Charger PD 20714mV / 3000mA, max 20000mV / 3000mA / 60000mW
        Port 2: SRC
    """

    command = ['ectool', 'usbpdpower']
    if self._pd_name:
      command.append('--name=' + self._pd_name)
    output = self._device.CheckOutput(command)

    USBPortInfo = collections.namedtuple(
        'USBPortInfo', 'id state voltage current')
    ports = []

    for line in output.strip().splitlines():
      match = re.match(r'Port\s+(\d+):\s+(\w+)', line)
      if not match:
        raise self.Error('unexpected output: %s' % output)
      port_id, port_state = int(match.group(1)), match.group(2)
      if port_state not in ['Disconnected', 'SNK', 'SRC']:
        raise self.Error('unexpected PD state: %s\noutput="""%s"""' %
                         (port_state, output))
      voltage = None
      current = None
      if port_state == 'SNK':
        match = re.search(r'SNK Charger PD (\d+)mV\s+/\s+(\d+)mA', line)
        if not match:
          raise self.Error('unexpected output for SNK state: %s' % output)
        voltage, current = int(match.group(1)), int(match.group(2))

      ports.append(USBPortInfo(port_id, port_state, voltage, current))
    return ports

  def GetInfoDict(self):
    """Returns a dict containing information about the battery.

    TODO(kitching): Determine whether this function is necessary (who uses it?).
    TODO(kitching): Use calls on the power object to get required information
                    instead of manually reading the Sysfs files.
    """
    def GetChargePctFloat():
      return self.GetChargePct(True) / 100

    _SysfsAttribute = collections.namedtuple(
        'SysfsAttribute',
        ['name', 'type', 'optional', 'getter'])
    _SysfsBatteryAttributes = [
        _SysfsAttribute('current_now', int, False, None),
        _SysfsAttribute('present', bool, False, None),
        _SysfsAttribute('status', str, False, None),
        _SysfsAttribute('voltage_now', int, False, None),
        _SysfsAttribute('voltage_min_design', int, True, None),
        _SysfsAttribute('energy_full', int, True, None),
        _SysfsAttribute('energy_full_design', int, True, None),
        _SysfsAttribute('energy_now', int, True, None),
        _SysfsAttribute('charge_full', int, True, self.GetChargeFull),
        _SysfsAttribute('charge_full_design', int, True,
                        self.GetBatteryDesignCapacity),
        _SysfsAttribute('charge_now', int, True, self.GetCharge),
        _SysfsAttribute('fraction_full', float, True, GetChargePctFloat),
    ]
    result = {}
    sysfs_path = self._battery_path
    if not sysfs_path:
      return result
    for k, item_type, optional, getter in _SysfsBatteryAttributes:
      result[k] = None
      try:
        value = (
            getter() if getter else
            self._device.ReadSpecialFile(
                self._device.path.join(sysfs_path, k)).strip())
        result[k] = item_type(value)
      except Exception as e:
        log_func = logging.debug if optional else logging.error
        exc_str = '%s: %s' % (e.__class__.__name__, e)
        if getter:
          log_func('sysfs attribute %s is unavailable: %s', k, exc_str)
        else:
          log_func('sysfs path %s is unavailable: %s',
                   self._device.path.join(sysfs_path, k), exc_str)
    return result


class ECToolPower(Power):
  # Regular expression for parsing output.
  EC_BATTERY_CHARGING_RE = re.compile(r'^\s+Flags\s+.*\s+CHARGING.*$',
                                      re.MULTILINE)
  BATTERY_FLAGS_RE = re.compile(r'Flags\s+(.*)$')

  def __init__(self, dut):
    super(ECToolPower, self).__init__(dut)

  def _GetECToolBatteryFlags(self):
    re_object = self.BATTERY_FLAGS_RE.findall(
        self._device.CallOutput(['ectool', 'battery']))
    if re_object:
      return re_object[0].split()
    else:
      return []

  def _GetECToolBatteryAttribute(self, key_name):
    re_object = re.findall(r'%s\s+(\d+)' % key_name,
                           self._device.CallOutput(['ectool', 'battery']))
    if re_object:
      return int(re_object[0])
    else:
      raise self.Error('Cannot find key "%s" in ectool battery' % key_name)

  def CheckACPresent(self):
    """See Power.CheckACPresent"""
    return 'AC_PRESENT' in self._GetECToolBatteryFlags()

  def CheckBatteryPresent(self):
    """See Power.CheckBatteryPresent"""
    return 'BATT_PRESENT' in self._GetECToolBatteryFlags()

  def GetCharge(self):
    """See Power.GetCharge"""
    return self._GetECToolBatteryAttribute('Remaining capacity')

  def GetChargeFull(self):
    """See Power.GetChargeFull"""
    return self._GetECToolBatteryAttribute('Last full charge:')

  def GetChargePct(self, get_float=False):
    """See Power.GetChargePct"""
    charge_pct = self.GetCharge() * 100.0 / self.GetChargeFull()
    if get_float:
      return charge_pct
    else:
      return round(charge_pct)

  def GetWearPct(self):
    """See Power.GetWearPct"""
    capacity = self.GetChargeFull()
    design_capacity = self.GetBatteryDesignCapacity()
    if design_capacity <= 0:
      return None  # Something wrong with the battery
    return 100 - round(capacity * 100.0 / design_capacity)

  def GetBatteryCurrent(self):
    """See Power.GetBatteryCurrent"""
    charging = 'CHARGING' in self._GetECToolBatteryFlags()
    current = self._GetECToolBatteryAttribute('Present current')
    return current if charging else -current

  def GetBatteryDesignCapacity(self):
    """See Power.GetBatteryDesignCapacity"""
    return self._GetECToolBatteryAttribute('Design capacity:')
