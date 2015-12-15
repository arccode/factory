#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve system information and status."""

from __future__ import print_function

import collections
import copy
import logging

import netifaces

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component


# Static list of known properties in SystemStatus.
_PROP_LIST = []


def StatusProperty(f):
  """Decoration function for SystemStatus properties."""
  global _PROP_LIST
  name = f.__name__
  if not name.startswith('_'):
    _PROP_LIST.append(name)
  @property
  def prop(self):
    if name in self._overrides:
      return self._overrides[name]
    try:
      return f(self)
    except:
      return None
  return prop


# TODO(hungte) These functions currently only reads local network information,
# and should be changed to support remote DUT (for example by using 'ip'
# command). We may also move them to class internal or shared network utility
# modules.
def GetIPv4Interfaces():
  """Returns a list of IPv4 interfaces."""
  interfaces = sorted(netifaces.interfaces())
  return [x for x in interfaces if not x.startswith('lo')]


def GetIPv4InterfaceAddresses(interface):
  """Returns a list of ips of an interface"""
  try:
    addresses = netifaces.ifaddresses(interface).get(netifaces.AF_INET, [])
  except ValueError:
    pass
  ips = [x.get('addr') for x in addresses
         if 'addr' in x] or ['none']
  return ips


def IsInterfaceConnected(prefix):
  """Returns whether any interface starting with prefix is connected"""
  ips = []
  for interface in GetIPv4Interfaces():
    if interface.startswith(prefix):
      ips += [x for x in GetIPv4InterfaceAddresses(interface) if x != 'none']

  return ips != []


def GetIPv4Addresses():
  """Returns a string describing interfaces' IPv4 addresses.

  The returned string is of the format

    eth0=192.168.1.10, wlan0=192.168.16.14
  """
  ret = []
  interfaces = GetIPv4Interfaces()
  for interface in interfaces:
    ips = GetIPv4InterfaceAddresses(interface)
    ret.append('%s=%s' % (interface, '+'.join(ips)))

  return ', '.join(ret)


_SysfsAttribute = collections.namedtuple('SysfsAttribute',
                                         ['name', 'type', 'optional'])
_SysfsBatteryAttributes = [
    _SysfsAttribute('charge_full', int, False),
    _SysfsAttribute('charge_full_design', int, False),
    _SysfsAttribute('charge_now', int, False),
    _SysfsAttribute('current_now', int, False),
    _SysfsAttribute('present', bool, False),
    _SysfsAttribute('status', str, False),
    _SysfsAttribute('voltage_now', int, False),
    _SysfsAttribute('voltage_min_design', int, True),
    _SysfsAttribute('energy_full', int, True),
    _SysfsAttribute('energy_full_design', int, True),
    _SysfsAttribute('energy_now', int, True),
]


class SystemStatusSnapshot(object):
  """A snapshot object allows accessing pre-fetched data."""
  def __init__(self, status):
    self.__dict__.update(copy.deepcopy(
        dict((name, getattr(status, name)) for name in _PROP_LIST)))


class SystemStatus(component.DUTComponent):
  """Information about the current system status.

  This is information that changes frequently, e.g., load average
  or battery information.
  """

  def __init__(self, dut=None):
    super(SystemStatus, self).__init__(dut)
    self._overrides = {}

  def Snapshot(self):
    """Returns a SystemStatusSnapshot object with all properties."""
    return SystemStatusSnapshot(self)

  def Overrides(self, name, value):
    """Overrides a status property to given value.

    This is useful for setting shared data like charge_manager.

    Args:
      name: A string for the property to override.
      value: The value to return in future for given property.
    """
    self._overrides[name] = value

  def _CalculateBatteryFractionFull(self, battery):
    for t in ['charge', 'energy']:
      now = battery['%s_now' % t]
      full = battery['%s_full' % t]
      if (now is not None and full is not None and full > 0 and now >= 0):
        return float(now) / full
    return None

  @StatusProperty
  def charge_manager(self):
    """The charge_manager instance for checking force charge status.

    This can be set by using Overrides('charge_manager', instance).
    """
    return None

  @StatusProperty
  def battery_sysfs_path(self):
    path_list = self._dut.Glob('/sys/class/power_supply/*/type')
    for p in path_list:
      try:
        if self._dut.ReadFile(p).strip() == 'Battery':
          return self._dut.path.dirname(p)
      except:
        logging.warning('sysfs path %s is unavailable', p)
    return None

  @StatusProperty
  def battery(self):
    result = {}
    sysfs_path = self.battery_sysfs_path
    for k, item_type, optional in _SysfsBatteryAttributes:
      result[k] = None
      try:
        if sysfs_path:
          result[k] = item_type(
              self._dut.ReadFile(self._dut.path.join(sysfs_path, k)).strip())
      except:
        log_func = logging.error
        if optional:
          log_func = logging.debug
        log_func('sysfs path %s is unavailable',
                 self._dut.path.join(sysfs_path, k))

    result['fraction_full'] = self._CalculateBatteryFractionFull(result)
    result['force'] = False
    if self.charge_manager:
      force_status = {
          self._dut.power.ChargeState.DISCHARGE: 'Discharging',
          self._dut.power.ChargeState.CHARGE: 'Charging',
          self._dut.power.ChargeState.IDLE: 'Idle'}.get(
              self.charge_manager.state)
      if force_status:
        result['status'] = force_status
        result['force'] = True
    return result

  @StatusProperty
  def fan_rpm(self):
    """Gets fan speed."""
    return self._dut.thermal.GetFanRPM()

  @StatusProperty
  def temperatures(self):
    """Gets temperatures from sensors."""
    return self._dut.thermal.GetTemperatures()

  @StatusProperty
  def main_temperature_index(self):
    return self._dut.thermal.GetMainTemperatureIndex()

  @StatusProperty
  def load_avg(self):
    return map(float, self._dut.ReadFile('/proc/loadavg').split()[0:3])

  @StatusProperty
  def cpu(self):
    return map(int,
               self._dut.ReadFile('/proc/stat').splitlines()[0].split()[1:])

  @StatusProperty
  def ips(self):
    return GetIPv4Addresses()

  @StatusProperty
  def eth_on(self):
    return IsInterfaceConnected('eth')

  @StatusProperty
  def wlan_on(self):
    return IsInterfaceConnected('mlan') or IsInterfaceConnected('wlan')


if __name__ == '__main__':
  import yaml
  from cros.factory.test import dut
  logging.basicConfig()
  status = SystemStatus(dut.Create())
  print(yaml.dump(status.Snapshot().__dict__, default_flow_style=False))
