#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve system information and status."""

from __future__ import print_function

import copy
import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component

from cros.factory.external import netifaces

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
    if name in self._overrides:  # pylint: disable=protected-access
      return self._overrides[name]  # pylint: disable=protected-access
    try:
      return f(self)
    except Exception:
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


class SystemStatusSnapshot(object):
  """A snapshot object allows accessing pre-fetched data."""
  def __init__(self, status_):
    self.__dict__.update(copy.deepcopy(
        dict((name, getattr(status_, name)) for name in _PROP_LIST)))


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

  @StatusProperty
  def charge_manager(self):
    """The charge_manager instance for checking force charge status.

    This can be set by using Overrides('charge_manager', instance).
    """
    return None

  @StatusProperty
  def battery(self):
    """Returns a dict containing information about the battery."""
    result = self._dut.power.GetInfoDict()
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
  from cros.factory.test import dut as dut_module
  logging.basicConfig()
  status = SystemStatus(dut_module.Create())
  print(yaml.dump(status.Snapshot().__dict__, default_flow_style=False))
