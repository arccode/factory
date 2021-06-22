# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import logging
import re
import statistics
import time

from cros.factory.device import device_types
from cros.factory.utils import type_utils


class PowerException(device_types.DeviceException):
  pass


def CreatePower(dut, *mixins, **kargs):
  """Creates an instance of Power class inherited from PowerBase with mixins.

  This function is equivalent to

  def CreatePower(dut, *mixins, **kargs):
    class Power(*mixins, PowerBase):
      pass
    return Power(dut, **kargs)

  except that we actually cannot use *mixins in class declaration.

  Args:
    dut: A device_types.DeviceBoard instance.
    mixins: One or more mixin classes.
    kargs: Key arguments to pass to base constructor.

  Returns:
    An instance of Power class with given mixins, with `dut` and `kargs` passed
    as constructor arguments.

  Example:
    power = CreatePower(dut, ECToolPowerControlMixin, ECToolPowerInfoMixin)
  """
  bases = mixins + (PowerBase,)
  power_cls = type('Power', bases, {})
  return power_cls(dut, **kargs)


class PowerBase(device_types.DeviceComponent):
  """Base class for power.

  The base class is basically empty, and needs mixin classes to add its
  functions.
  """

  # Power source types
  PowerSource = type_utils.Enum(['BATTERY', 'AC'])

  # An enumeration of possible charge states.
  # - ``CHARGE``: Charge the device as usual.
  # - ``IDLE``: Do not charge the device, even if connected to mains.
  # - ``DISCHARGE``: Force the device to discharge.
  # - ``FULL``: Full charge states.
  ChargeState = type_utils.Enum(['CHARGE', 'IDLE', 'DISCHARGE', 'FULL'])

  def __init__(self, dut, pd_name=None):
    super(PowerBase, self).__init__(dut)
    self._pd_name = pd_name


class PowerControlMixinBase:
  """Base class for power control mixin."""

  def SetChargeState(self, state):
    """Sets the charge state."""
    raise NotImplementedError


class DummyPowerControlMixin(PowerControlMixinBase):
  """Power control mixin that does nothing."""

  def SetChargeState(self, state):
    """See PowerControlMixinBase.SetChargeState"""


class ECToolPowerControlMixin(PowerControlMixinBase):
  """Power control mixin that uses ectool."""

  def SetChargeState(self, state):
    """See PowerControlMixinBase.SetChargeState"""
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


class PowerInfoMixinBase:
  """Base class for power info mixin."""

  _CHARGE_STATE_MAP = {
      'Charging': PowerBase.ChargeState.CHARGE,
      'Idle': PowerBase.ChargeState.IDLE,
      'Discharging': PowerBase.ChargeState.DISCHARGE,
      'Full': PowerBase.ChargeState.FULL
  }

  def CheckACPresent(self):
    """Check if AC power is present."""
    raise NotImplementedError

  def GetACType(self):
    """Get AC power type."""
    raise NotImplementedError

  def CheckBatteryPresent(self):
    """Check if battery is present."""
    raise NotImplementedError

  def GetCharge(self):
    """Get current charge level in mAh."""
    raise NotImplementedError

  def GetChargeMedian(self, read_count=10):
    """Read charge level several times and return the median."""
    charge_nows = []
    for unused_i in range(read_count):
      charge_now = self.GetCharge()
      if charge_now:
        charge_nows.append(charge_now)
      time.sleep(0.1)
    return statistics.median(charge_nows)

  def GetChargeFull(self):
    """Get full charge level in mAh."""
    raise NotImplementedError

  def GetChargePct(self, get_float=False):
    """Get current charge level in percentage.

    Args:
      get_float: Returns charge percentage in float.

    Returns:
      Charge percentage in int/float.
    """
    raise NotImplementedError

  def GetWearPct(self):
    """Get current battery wear in percentage of new capacity."""
    raise NotImplementedError

  def GetChargeState(self):
    """Returns the charge state.

    Returns:
      One of the three states in ChargeState.
    """
    raise NotImplementedError

  def GetChargerCurrent(self):
    """Gets the amount of current we ask from charger.

    Returns:
      Interger value in mA.
    """
    raise NotImplementedError

  def GetBatteryCurrent(self):
    """Gets the amount of current battery is charging/discharging at.

    Returns:
      Integer value in mA.
    """
    raise NotImplementedError

  def GetBatteryDesignCapacity(self):
    """Gets battery's design capacity.

    Returns:
      Battery's design capacity in mAh.

    Raises:
      DeviceException if battery's design capacity cannot be obtained.
    """
    raise NotImplementedError

  def GetBatteryVoltage(self):
    """Gets battery's current voltage.

    Returns:
      Battery's current voltage in mV.
    """
    raise NotImplementedError

  def GetBatteryCycleCount(self):
    """Gets battery's cycle count."""
    raise NotImplementedError

  def GetBatteryManufacturer(self):
    """Gets battery's manufacturer."""
    raise NotImplementedError

  def GetInfoDict(self):
    """Returns a dict containing information about the battery.

    TODO(kitching): Determine whether this function is necessary (who uses it?).
    """
    _SysfsBatteryAttributes = [
        ('current_now', self.GetBatteryCurrent),
        ('present', self.CheckBatteryPresent),
        ('status', self.GetChargeState),
        ('voltage_now', self.GetBatteryVoltage),
        ('charge_full', self.GetChargeFull),
        ('charge_full_design', self.GetBatteryDesignCapacity),
        ('charge_now', self.GetCharge),
        ('fraction_full', lambda: self.GetChargePct(True) / 100),
    ]
    result = {}
    for k, getter in _SysfsBatteryAttributes:
      try:
        result[k] = getter()
      except Exception as e:
        exc_str = '%s: %s' % (e.__class__.__name__, e)
        logging.error('battery attribute %s is unavailable: %s', k, exc_str)
    return result


class SysfsPowerInfoMixin(PowerInfoMixinBase):
  """Power info mixin that uses sysfs files."""

  _sys = '/sys'
  # Regular expression for parsing charger current.
  EC_CHARGER_CURRENT_RE = re.compile(r'^chg_current = (\d+)mA', re.MULTILINE)

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
    """See PowerInfoMixinBase.CheckACPresent"""
    try:
      p = self.FindPowerPath(self.PowerSource.AC)
      return self.ReadOneLine(self._device.path.join(p, 'online')) == '1'
    except (PowerException, IOError):
      return False

  def GetACType(self):
    """See PowerInfoMixinBase.GetACType"""
    try:
      p = self.FindPowerPath(self.PowerSource.AC)
      return self.ReadOneLine(self._device.path.join(p, 'type'))
    except (PowerException, IOError):
      return 'Unknown'

  @device_types.DeviceProperty
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
    """See PowerInfoMixinBase.CheckBatteryPresent"""
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
    """See PowerInfoMixinBase.GetCharge"""
    charge_now = self.GetBatteryAttribute('charge_now')
    if charge_now:
      return int(charge_now) // 1000
    return None

  def GetChargeFull(self):
    """See PowerInfoMixinBase.GetChargeFull"""
    charge_full = self.GetBatteryAttribute('charge_full')
    if charge_full:
      return int(charge_full) // 1000
    return None

  def GetChargePct(self, get_float=False):
    """See PowerInfoMixinBase.GetChargePct"""
    now = self.GetBatteryAttribute('charge_now')
    full = self.GetBatteryAttribute('charge_full')
    if now is None or full is None:
      now = self.GetBatteryAttribute('energy_now')
      full = self.GetBatteryAttribute('energy_full')
      if now is None or full is None:
        return None

    if float(full) <= 0:
      return None  # Something wrong with the battery
    charge_pct = float(now) * 100 / float(full)
    if get_float:
      return charge_pct
    return round(charge_pct)

  def GetWearPct(self):
    """See PowerInfoMixinBase.GetWearPct"""
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
    return 100 - (round(capacity * 100 / float(design_capacity)))

  def GetChargeState(self):
    """See PowerInfoMixinBase.GetChargeState"""
    return self._CHARGE_STATE_MAP[self.GetBatteryAttribute('status')]

  def GetChargerCurrent(self):
    """See PowerInfoMixinBase.GetChargerCurrent

    TODO(chenghan): Currently cros-usb-pd-charger does not provide 'current_now'
                    file in sysfs (crbug/807753), so we use ectool to get this
                    information. Change this function to use 'current_now' when
                    the issue is fixed.
    """
    re_object = self.EC_CHARGER_CURRENT_RE.findall(
        self._device.CheckOutput(['ectool', 'chargestate', 'show']))
    if re_object:
      return int(re_object[0])
    raise self.Error('Cannot find current in ectool chargestate show')

  def GetBatteryCurrent(self):
    """See PowerInfoMixinBase.GetBatteryCurrent"""
    charging = (self.GetBatteryAttribute('status') == 'Charging')
    current = self.GetBatteryAttribute('current_now')
    if current is None:
      raise self.Error('Cannot find %s/current_now' % self._battery_path)
    current_ma = abs(int(current)) // 1000
    return current_ma if charging else -current_ma

  def GetBatteryDesignCapacity(self):
    """See PowerInfoMixinBase.GetBatteryDesignCapacity"""
    design_capacity = self.GetBatteryAttribute('charge_full_design')
    if design_capacity is None:
      raise self.Error('Design capacity not found.')
    try:
      return int(design_capacity) // 1000
    except Exception as e:
      raise self.Error('Unable to get battery design capacity: %s' % e)

  def GetBatteryVoltage(self):
    """See PowerInfoMixinBase.GetBatteryVoltage"""
    voltage = self.GetBatteryAttribute('voltage_now')
    return int(voltage) // 1000

  def GetBatteryCycleCount(self):
    """See PowerInfoMixinBase.GetBatteryCycleCount"""
    return int(self.GetBatteryAttribute('cycle_count'))

  def GetBatteryManufacturer(self):
    """See PowerInfoMixinBase.GetBatteryManufacturer"""
    return self.GetBatteryAttribute('manufacturer')


class ECToolPowerInfoMixin(PowerInfoMixinBase):
  """Power info mixin that uses ectool."""

  # Regular expression for parsing output.
  EC_BATTERY_CHARGING_RE = re.compile(r'^\s+Flags\s+.*\s+CHARGING.*$',
                                      re.MULTILINE)
  EC_CHARGER_CURRENT_RE = re.compile(r'^chg_current = (\d+)mA', re.MULTILINE)
  BATTERY_FLAGS_RE = re.compile(r'Flags\s+(.*)$')

  def _GetECToolBatteryFlags(self):
    re_object = self.BATTERY_FLAGS_RE.findall(
        self._device.CallOutput(['ectool', 'battery']))
    if re_object:
      return re_object[0].split()
    return []

  def _GetECToolBatteryAttribute(self, key_name, item_type=str):
    re_object = re.findall(r'%s\s+(\S+)' % key_name,
                           self._device.CallOutput(['ectool', 'battery']))
    if re_object:
      return item_type(re_object[0])
    raise self.Error('Cannot find key "%s" in ectool battery' % key_name)

  def CheckACPresent(self):
    """See PowerInfoMixinBase.CheckACPresent"""
    return 'AC_PRESENT' in self._GetECToolBatteryFlags()

  def GetACType(self):
    """See PowerInfoMixinBase.GetACType.

    There is no ectool command to get AC type, so just return 'Unknown'.
    """
    return 'Unknown'

  def CheckBatteryPresent(self):
    """See PowerInfoMixinBase.CheckBatteryPresent"""
    return 'BATT_PRESENT' in self._GetECToolBatteryFlags()

  def GetCharge(self):
    """See PowerInfoMixinBase.GetCharge"""
    return self._GetECToolBatteryAttribute('Remaining capacity', int)

  def GetChargeFull(self):
    """See PowerInfoMixinBase.GetChargeFull"""
    return self._GetECToolBatteryAttribute('Last full charge:', int)

  def GetChargePct(self, get_float=False):
    """See PowerInfoMixinBase.GetChargePct"""
    charge_pct = self.GetCharge() * 100 / self.GetChargeFull()
    if get_float:
      return charge_pct
    return round(charge_pct)

  def GetWearPct(self):
    """See PowerInfoMixinBase.GetWearPct"""
    capacity = self.GetChargeFull()
    design_capacity = self.GetBatteryDesignCapacity()
    if design_capacity <= 0:
      return None  # Something wrong with the battery
    return 100 - round(capacity * 100 / design_capacity)

  def GetChargeState(self):
    """See PowerInfoMixinBase.GetWearPct"""
    if 'CHARGING' in self._GetECToolBatteryFlags():
      return self.ChargeState.CHARGE
    return self.ChargeState.DISCHARGE

  def GetBatteryCurrent(self):
    """See PowerInfoMixinBase.GetBatteryCurrent"""
    charging = 'CHARGING' in self._GetECToolBatteryFlags()
    current = self._GetECToolBatteryAttribute('Present current', int)
    return current if charging else -current

  def GetBatteryDesignCapacity(self):
    """See PowerInfoMixinBase.GetBatteryDesignCapacity"""
    return self._GetECToolBatteryAttribute('Design capacity:', int)

  def GetChargerCurrent(self):
    """See PowerInfoMixinBase.GetChargerCurrent"""
    re_object = self.EC_CHARGER_CURRENT_RE.findall(
        self._device.CheckOutput(['ectool', 'chargestate', 'show']))
    if re_object:
      return int(re_object[0])
    raise self.Error('Cannot find current in ectool chargestate show')

  def GetBatteryVoltage(self):
    """See PowerInfoMixinBase.GetBatteryVoltage"""
    return self._GetECToolBatteryAttribute('Present voltage', int)

  def GetBatteryCycleCount(self):
    """See PowerInfoMixinBase.GetBatteryCycleCount"""
    return self._GetECToolBatteryAttribute('Cycle count', int)

  def GetBatteryManufacturer(self):
    """See PowerInfoMixinBase.GetBatteryManufacturer"""
    return self._GetECToolBatteryAttribute('OEM name:')

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


class PowerDaemonPowerInfoMixin(PowerInfoMixinBase):
  """Power info mixin that uses powerd."""

  def _GetDumpPowerStatus(self):
    return self._device.CallOutput(['dump_power_status'])

  def _GetPowerAttribute(self, key_name, item_type=str):
    re_object = re.findall(
        r'^%s ?(\S*)$' % key_name, self._GetDumpPowerStatus(), re.MULTILINE)
    if re_object:
      return item_type(re_object[0])
    raise self.Error('Cannot find key "%s" in dump_power_status' % key_name)

  def CheckACPresent(self):
    """See PowerInfoMixinBase.CheckACPresent"""
    return self._GetPowerAttribute('line_power_connected', int) == 1

  def GetACType(self):
    """See PowerInfoMixinBase.GetACType"""
    return self._GetPowerAttribute('line_power_type')

  def CheckBatteryPresent(self):
    """See PowerInfoMixinBase.CheckBatteryPresent"""
    return self._GetPowerAttribute('battery_present', int) == 1

  def GetCharge(self):
    """See PowerInfoMixinBase.GetCharge"""
    return int(self._GetPowerAttribute('battery_charge', float) * 1000)

  def GetChargeFull(self):
    """See PowerInfoMixinBase.GetChargeFull"""
    return int(self._GetPowerAttribute('battery_charge_full', float) * 1000)

  def GetChargePct(self, get_float=False):
    """See PowerInfoMixinBase.GetChargePct"""
    charge_pct = self._GetPowerAttribute('battery_percent', float)
    if get_float:
      return charge_pct
    return round(charge_pct)

  def GetWearPct(self):
    """See PowerInfoMixinBase.GetWearPct"""
    capacity = self.GetChargeFull()
    design_capacity = self.GetBatteryDesignCapacity()
    if design_capacity <= 0:
      return None  # Something wrong with the battery
    return 100 - round(capacity * 100 / design_capacity)

  def GetChargeState(self):
    """See PowerInfoMixinBase.GetChargeState"""
    return self._CHARGE_STATE_MAP[self._GetPowerAttribute('battery_status')]

  # pylint: disable=useless-super-delegation
  def GetChargerCurrent(self):
    """See PowerInfoMixinBase.GetChargerCurrent

    TODO(chenghan): Currently cros-usb-pd-charger does not provide 'current_now'
                    file in sysfs (crbug/807753), which is read by
                    `dump_power_status` to get 'line_power_current' field.
                    Change this function to use 'line_power_current' when the
                    issue is fixed.
    """
    return super(PowerDaemonPowerInfoMixin, self).GetChargerCurrent()

  def GetBatteryCurrent(self):
    """See PowerInfoMixinBase.GetBatteryCurrent"""
    charging = self.GetChargeState() == self.ChargeState.CHARGE
    current = int(self._GetPowerAttribute('battery_current', float) * 1000)
    return current if charging else -current

  def GetBatteryDesignCapacity(self):
    """See PowerInfoMixinBase.GetBatteryDesignCapacity"""
    return int(
        self._GetPowerAttribute('battery_charge_full_design', float) * 1000)

  def GetBatteryVoltage(self):
    """See PowerInfoMixinBase.GetBatteryVoltage"""
    return int(
        self._GetPowerAttribute('battery_voltage', float) * 1000)

  # pylint: disable=useless-super-delegation
  def GetBatteryCycleCount(self):
    """See PowerInfoMixinBase.GetBatteryCycleCount

    TODO(chenghan): Change this function when `dump_power_status` supports
                    this field.
    """
    return super(PowerDaemonPowerInfoMixin, self).GetBatteryCycleCount()

  # pylint: disable=useless-super-delegation
  def GetBatteryManufacturer(self):
    """See PowerInfoMixinBase.GetBatteryManufacturer

    TODO(chenghan): Change this function when `dump_power_status` supports
                    this field.
    """
    return super(PowerDaemonPowerInfoMixin, self).GetBatteryManufacturer()


class LinuxPower(DummyPowerControlMixin, SysfsPowerInfoMixin, PowerBase):
  """Power with no power control and info from sysfs."""


class ChromeOSPowerLegacy(
    ECToolPowerControlMixin, SysfsPowerInfoMixin, PowerBase):
  """Power with ectool power control and info from sysfs."""


class ChromeOSPower(ECToolPowerControlMixin, PowerDaemonPowerInfoMixin,
                    ECToolPowerInfoMixin, PowerBase):
  """Power with ectool power control and info from powerd.

  If powerd does not support the function, fall back to use ectool.
  """


# Some board implementations create their own power class by inheriting from
# power.Power, which is the previous power class with ectool power control
# and sysfs power info. For compatibility we also define Power here.
Power = ChromeOSPowerLegacy
