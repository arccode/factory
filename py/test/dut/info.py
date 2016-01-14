#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve non-volatile system information."""

from __future__ import print_function

import copy
import re

import factory_common  # pylint: disable=W0611
from cros.factory import hwid
from cros.factory import test
from cros.factory.test import factory
from cros.factory.test.dut import component
from cros.factory.utils.sys_utils import MountDeviceAndReadFile


# Static list of known properties in SystemInfo.
_INFO_PROP_LIST = []


def InfoProperty(f):
  """Decoration function for SystemInfo properties."""
  global _INFO_PROP_LIST
  name = f.__name__
  if not name.startswith('_'):
    _INFO_PROP_LIST.append(name)
  @property
  def prop(self):
    if name in self._overrides:
      return self._overrides[name]
    if name in self._cached:
      return self._cached[name]
    value = None
    try:
      value = f(self)
    except:
      pass
    self._cached[name] = value
    return value
  return prop


class SystemInfo(component.DUTComponent):
  """Static information about the system.

  This is mostly static information that changes rarely if ever
  (e.g., version numbers, serial numbers, etc.).

  You can access the information by reading individual properties. However all
  values are cached by default unless you call Reload(name). Calling Reload()
  without giving particular name will refresh all properties.

  To get a dictionary object of all properties, use GetAll().
  You can also "override" some properties by using Overrides(name, value).
  """

  def __init__(self, _dut=None):
    super(SystemInfo, self).__init__(_dut)
    self._cached = {}
    self._overrides = {}

  def GetAll(self):
    """Returns all properties in a dictionary object."""
    return copy.deepcopy(
        dict((name, getattr(self, name)) for name in _INFO_PROP_LIST))

  def Reload(self, name=None):
    """Reloads a property in system information object.

    When name is omitted, reload all properties.

    Args:
      name: A string for the property to be refreshed.
    """
    if name is not None:
      self._cached.pop(name, None)
    else:
      self._cached.clear()

  def Overrides(self, name, value):
    """Overrides an information property to given value.

    This is useful for setting shared information like update_md5sum.

    Args:
      name: A string for the property to override.
      value: The value to return in future for given property.
    """
    self._overrides[name] = value

  @InfoProperty
  def cpu_count(self):
    """Gets number of CPUs on the machine"""
    output = self._dut.CallOutput('lscpu')
    match = re.search(r'^CPU\(s\):\s*(\d+)', output, re.MULTILINE)
    return int(match.group(1)) if match else None

  @InfoProperty
  def memory_total_kb(self):
    """Gets total memory of system in kB"""
    output = self._dut.CallOutput('cat /proc/meminfo')
    match = re.search(r'^MemTotal:\s*(\d+)', output, re.MULTILINE)
    return int(match.group(1)) if match else None

  @InfoProperty
  def release_image_version(self):
    """Version of the image on release partition."""
    return self._release_lsb_data['GOOGLE_RELEASE']

  @InfoProperty
  def release_image_channel(self):
    """Channel of the image on release partition."""
    return self._release_lsb_data['CHROMEOS_RELEASE_TRACK']

  @InfoProperty
  def mlb_serial_number(self):
    """Mother board serial number."""
    return test.shopfloor.GetDeviceData()['mlb_serial_number']

  @InfoProperty
  def serial_number(self):
    """Device serial number (usually printed on device package)."""
    return test.shopfloor.get_serial_number()

  @InfoProperty
  def stage(self):
    """Manufacturing build stage. Examples: PVT, EVT, DVT."""
    return test.shopfloor.GetDeviceData()['stage']

  @InfoProperty
  def factory_image_version(self):
    """Version of the image on factory test partition."""
    lsb_release = self._dut.ReadFile('/etc/lsb-release')
    match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release, re.MULTILINE)
    return match.group(1) if match else None

  @InfoProperty
  def wlan0_mac(self):
    """MAC address of first wireless network device."""
    for wlan_interface in ['wlan0', 'mlan0']:
      address_path = self._dut.path.join('/sys/class/net/',
                                         wlan_interface, 'address')
      if self._dut.path.exists(address_path):
        return self._dut.ReadFile(address_path).strip()

  @InfoProperty
  def eth_macs(self):
    """MAC addresses of ethernet devices."""
    macs = dict()
    eth_paths = self._dut.Glob('/sys/class/net/eth*')
    for eth_path in eth_paths:
      address_path = self._dut.path.join(eth_path, 'address')
      if self._dut.path.exists(address_path):
        macs[self._dut.path.basename(eth_path)] = self._dut.ReadFile(
            address_path).strip()
    return macs

  @InfoProperty
  def toolkit_version(self):
    """Version of ChromeOS factory toolkit."""
    return self._dut.ReadFile('/usr/local/factory/TOOLKIT_VERSION').strip()

  @InfoProperty
  def kernel_version(self):
    """Version of running kernel."""
    return self._dut.CallOutput(['uname', '-r']).strip()

  @InfoProperty
  def architecture(self):
    """System architecture."""
    return self._dut.CallOutput(['uname', '-m']).strip()

  @InfoProperty
  def root_device(self):
    """The root partition that boots current system."""
    return self._dut.CallOutput(['rootdev', '-s']).strip()

  @InfoProperty
  def firmware_version(self):
    """Version of main firmware."""
    return self._dut.CallOutput(['crossystem', 'fwid']).strip()

  @InfoProperty
  def ro_firmware_version(self):
    """Version of RO main firmware."""
    return self._dut.CallOutput(['crossystem', 'ro_fwid']).strip()

  @InfoProperty
  def mainfw_type(self):
    """Type of main firmware."""
    return self._dut.CallOutput(['crossystem', 'mainfw_type']).strip()

  @InfoProperty
  def board_version(self):
    return self._dut.CallOutput(['mosys', 'platform', 'version']).strip()

  @InfoProperty
  def ec_version(self):
    """Version of embedded controller."""
    return self._dut.ec.GetECVersion().strip()

  @InfoProperty
  def pd_version(self):
    return self._dut.usb_c.GetPDVersion().strip()

  @InfoProperty
  def factory_md5sum(self):
    """MD5 checksum of factory software."""
    return factory.get_current_md5sum()

  @InfoProperty
  def update_md5sum(self):
    """Indicates if an update is available on server.

    Usually set by using Overrides after checking shopfloor server.
    """
    return None

  @InfoProperty
  def _release_lsb_data(self):
    """Returns the lsb-release data in dict from release image partition."""
    release_rootfs = self._dut.partitions.RELEASE_ROOTFS.path
    # TODO(hungte) Change MountDeviceAndReadFile to DUT-aware.
    lsb_content = MountDeviceAndReadFile(release_rootfs, '/etc/lsb-release')
    return dict(re.findall('^(.+)=(.+)$', lsb_content, re.MULTILINE))

  @InfoProperty
  def hwid_database_version(self):
    """Uses checksum of hwid file as hwid database version."""
    hwid_file_path = self._dut.path.join(hwid.common.DEFAULT_HWID_DATA_PATH,
                                         hwid.common.ProbeBoard().upper())
    if self._dut.path.exists(hwid_file_path):
      # TODO(hungte) Support remote DUT.
      return hwid.hwid_utils.ComputeDatabaseChecksum(hwid_file_path)
    return None


if __name__ == '__main__':
  import yaml
  from cros.factory.test import dut
  info = SystemInfo(dut.Create())
  print(yaml.dump(info.GetAll(), default_flow_style=False))
