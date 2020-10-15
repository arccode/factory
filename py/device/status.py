#!/usr/bin/env python3
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve system information and status."""

import copy
import functools
import logging

from cros.factory.device import device_types

from cros.factory.external import netifaces

# Static list of known properties in SystemStatus.
_PROP_LIST = []


def StatusProperty(f):
  """Decoration function for SystemStatus properties."""
  name = f.__name__
  if not name.startswith('_'):
    _PROP_LIST.append(name)
  @property
  @functools.wraps(f)
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


class SystemStatusSnapshot:
  """A snapshot object allows accessing pre-fetched data."""
  def __init__(self, status_):
    self.__dict__.update(copy.deepcopy(
        {name: getattr(status_, name) for name in _PROP_LIST}))


class SystemStatus(device_types.DeviceComponent):
  """Information about the current system status.

  This is information that changes frequently, e.g., load average
  or battery information.
  """

  def __init__(self, device=None):
    super(SystemStatus, self).__init__(device)
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

  def _GetDefaultRouteInterface(self):
    """Returns the interface for default route."""
    routes = self._device.CallOutput('ip route show table 0 | grep default')
    if routes is None:
      return None
    # The output looks like 'default via 123.12.0.1 dev eth0 metric 1', and we
    # want the 'eth0' field.
    return routes.split()[4]

  @StatusProperty
  def charge_manager(self):
    """The charge_manager instance for checking force charge status.

    This can be set by using Overrides('charge_manager', instance).
    """
    return None

  @StatusProperty
  def battery(self):
    """Returns a dict containing battery charge fraction and state."""
    # If the below calls raise PowerException, the machine probably doesn't
    # have a battery.  Leave the values as `None` in this case.
    try:
      charge_fraction = self._device.power.GetChargePct(get_float=True) / 100
    except Exception:
      charge_fraction = None

    try:
      charge_state = self._device.power.GetChargeState()
    except Exception:
      charge_state = None

    return {'charge_fraction': charge_fraction,
            'charge_state': charge_state}

  @StatusProperty
  def fan_rpm(self):
    """Gets fan speed."""
    return self._device.fan.GetFanRPM()

  @StatusProperty
  def temperature(self):
    """Gets main (CPU) temperature from thermal sensor."""
    return self._device.thermal.GetTemperature()

  @StatusProperty
  def load_avg(self):
    return list(map(
        float, self._device.ReadFile('/proc/loadavg').split()[0:3]))

  @StatusProperty
  def cpu(self):
    return list(map(
        int, self._device.ReadFile('/proc/stat').splitlines()[0].split()[1:]))

  @StatusProperty
  def ips(self):
    return GetIPv4Addresses()

  @StatusProperty
  def eth_on(self):
    return IsInterfaceConnected('eth')

  @StatusProperty
  def wlan_on(self):
    return IsInterfaceConnected('mlan') or IsInterfaceConnected('wlan')

  @StatusProperty
  def ip(self):
    default_interface = self._GetDefaultRouteInterface()
    if default_interface is None:
      return None
    return GetIPv4InterfaceAddresses(default_interface)


def main():
  import pprint
  from cros.factory.device import device_utils
  logging.basicConfig()
  status = SystemStatus(device_utils.CreateDUTInterface())
  pprint.pprint(status.Snapshot().__dict__)


if __name__ == '__main__':
  main()
