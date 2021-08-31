#!/usr/bin/env python3
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve non-volatile system information."""

import copy
import logging
import os
import re

from cros.factory.device import device_types
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test import device_data
from cros.factory.test.env import paths
from cros.factory.test.rules import phase
from cros.factory.test import session
from cros.factory.utils import net_utils
from cros.factory.utils.sys_utils import MountDeviceAndReadFile


# Static list of known properties in SystemInfo.
_INFO_PROP_LIST = []


def InfoProperty(f):
  """Decoration function for SystemInfo properties."""
  name = f.__name__
  if not name.startswith('_'):
    _INFO_PROP_LIST.append(name)
  @property
  def prop(self):
    # pylint: disable=protected-access
    if name in self._overrides:
      return self._overrides[name]
    if name in self._cached:
      return self._cached[name]
    value = None
    try:
      value = f(self)
    except Exception:
      pass
    self._cached[name] = value
    return value
  return prop


class SystemInfo(device_types.DeviceComponent):
  """Static information about the system.

  This is mostly static information that changes rarely if ever
  (e.g., version numbers, serial numbers, etc.).

  You can access the information by reading individual properties. However all
  values are cached by default unless you call Invalidate(name). Calling
  Invalidate() without giving particular name will invalidate all properties.

  To get a dictionary object of all properties, use GetAll().
  To refresh, do Invalidate() then GetAll().
  You can also "override" some properties by using Overrides(name, value).
  """

  _FIRMWARE_NV_INDEX = 0x1007
  _FLAG_VIRTUAL_DEV_MODE_ON = 0x02

  def __init__(self, device=None):
    super(SystemInfo, self).__init__(device)
    self._cached = {}
    self._overrides = {}

  def GetAll(self):
    """Returns all properties in a dictionary object."""
    return copy.deepcopy(
        {name: getattr(self, name) for name in _INFO_PROP_LIST})

  def Invalidate(self, name=None):
    """Invalidates a property in system information object in cache.

    When name is omitted, invalidate all properties.

    Args:
      name: A string for the property to be refreshed.
    """
    if name is not None:
      self._cached.pop(name, None)
    else:
      self._cached.clear()

  def Overrides(self, name, value):
    """Overrides an information property to given value.

    This is useful for setting shared information like update_toolkit_version.

    Args:
      name: A string for the property to override.
      value: The value to return in future for given property.
    """
    self._overrides[name] = value

  @InfoProperty
  def cpu_count(self):
    """Gets number of CPUs on the machine"""
    output = self._device.CallOutput('lscpu')
    match = re.search(r'^CPU\(s\):\s*(\d+)', output, re.MULTILINE)
    return int(match.group(1)) if match else None

  @InfoProperty
  def memory_total_kb(self):
    return self._device.memory.GetTotalMemoryKB()

  @InfoProperty
  def release_image_version(self):
    """Version of the image on release partition."""
    # pylint: disable=unsubscriptable-object
    return self._release_lsb_data['GOOGLE_RELEASE']

  @InfoProperty
  def release_image_channel(self):
    """Channel of the image on release partition."""
    # pylint: disable=unsubscriptable-object
    return self._release_lsb_data['CHROMEOS_RELEASE_TRACK']

  def ClearSerialNumbers(self):
    """Clears any serial numbers from DeviceData."""
    return device_data.ClearAllSerialNumbers()

  def GetAllSerialNumbers(self):
    """Returns all available serial numbers in a dict."""
    return device_data.GetAllSerialNumbers()

  def GetSerialNumber(self, name=device_data.NAME_SERIAL_NUMBER):
    """Retrieves a serial number from device.

    Tries to load the serial number from DeviceData.  If not found, loads
    from DUT storage, and caches into DeviceData.
    """
    if not device_data.GetSerialNumber(name):
      serial = self._device.storage.LoadDict().get(name)
      if serial:
        device_data.UpdateSerialNumbers({name: serial})
    return device_data.GetSerialNumber(name)

  @InfoProperty
  def serial_number(self):
    """Device serial number (usually printed on device package)."""
    return self.GetSerialNumber()

  @InfoProperty
  def mlb_serial_number(self):
    """Motherboard serial number."""
    return self.GetSerialNumber(device_data.NAME_MLB_SERIAL_NUMBER)

  @InfoProperty
  def stage(self):
    """Manufacturing build stage. Examples: PVT, EVT, DVT."""
    # TODO(hungte) Umpire thinks this should be SMT, FATP, etc. Goofy monitor
    # simply displays this. We should figure out different terms for both and
    # find out the right way to print this value.
    return str(phase.GetPhase())

  @InfoProperty
  def test_image_version(self):
    """Version of the image on factory test partition."""
    lsb_release = self._device.ReadFile('/etc/lsb-release')
    match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release, re.MULTILINE)
    return match.group(1) if match else None

  @InfoProperty
  def test_image_builder_path(self):
    """Builder path of the image on factory test partition."""
    lsb_release = self._device.ReadFile('/etc/lsb-release')
    match = re.search('^CHROMEOS_RELEASE_BUILDER_PATH=(.+)$', lsb_release,
                      re.MULTILINE)
    return match.group(1) if match else None

  @InfoProperty
  def factory_image_version(self):
    """Version of the image on factory test partition.

    This is same as test_image_version.
    """
    return self.test_image_version

  @InfoProperty
  def wlan0_mac(self):
    """MAC address of first wireless network device."""
    for wlan_interface in ['wlan0', 'mlan0']:
      address_path = self._device.path.join(
          '/sys/class/net/', wlan_interface, 'address')
      if self._device.path.exists(address_path):
        return self._device.ReadFile(address_path).strip()
    return None

  @InfoProperty
  def eth_macs(self):
    """MAC addresses of ethernet devices."""
    macs = dict()
    eth_paths = sum([self._device.Glob(os.path.join('/sys/class/net', pattern))
                     for pattern in net_utils.DEFAULT_ETHERNET_NAME_PATTERNS],
                    [])
    for eth_path in eth_paths:
      address_path = self._device.path.join(eth_path, 'address')
      if self._device.path.exists(address_path):
        interface = self._device.path.basename(eth_path)
        macs[interface] = self._device.ReadSpecialFile(address_path).strip()
    return macs

  @InfoProperty
  def toolkit_version(self):
    """Version of ChromeOS factory toolkit."""
    return self._device.ReadFile(paths.FACTORY_TOOLKIT_VERSION_PATH).rstrip()

  @InfoProperty
  def kernel_version(self):
    """Version of running kernel."""
    return self._device.CallOutput(['uname', '-r']).strip()

  @InfoProperty
  def architecture(self):
    """System architecture."""
    return self._device.CallOutput(['uname', '-m']).strip()

  @InfoProperty
  def root_device(self):
    """The root partition that boots current system."""
    return self._device.CallOutput(['rootdev', '-s']).strip()

  @InfoProperty
  def firmware_version(self):
    """Version of main firmware."""
    return self._device.CallOutput(['crossystem', 'fwid']).strip()

  @InfoProperty
  def ro_firmware_version(self):
    """Version of RO main firmware."""
    return self._device.CallOutput(['crossystem', 'ro_fwid']).strip()

  @InfoProperty
  def mainfw_type(self):
    """Type of main firmware."""
    return self._device.CallOutput(['crossystem', 'mainfw_type']).strip()

  @InfoProperty
  def ec_version(self):
    """Version of embedded controller."""
    return self._device.ec.GetECVersion().strip()

  @InfoProperty
  def pd_version(self):
    return self._device.usb_c.GetPDVersion().strip()

  @InfoProperty
  def update_toolkit_version(self):
    """Indicates if an update is available on server.

    Usually set by using Overrides after checking shopfloor server.
    """
    # TODO(youcheng) Implement this in another way. Probably move this to goofy
    # state variables.
    return None

  @InfoProperty
  def _release_lsb_data(self):
    """Returns the lsb-release data in dict from release image partition."""
    release_rootfs = self._device.partitions.RELEASE_ROOTFS.path
    lsb_content = MountDeviceAndReadFile(
        release_rootfs, '/etc/lsb-release', dut=self._device)
    return dict(re.findall('^(.+)=(.+)$', lsb_content, re.MULTILINE))

  @InfoProperty
  def hwid_database_version(self):
    """Uses checksum of hwid file as hwid database version."""
    hwid_file_path = self._device.path.join(
        hwid_utils.GetDefaultDataPath(), hwid_utils.ProbeProject().upper())
    # TODO(hungte) Support remote DUT.
    return hwid_utils.ComputeDatabaseChecksum(hwid_file_path)

  @InfoProperty
  def pci_device_number(self):
    """Returns number of PCI devices."""
    res = self._device.CheckOutput(['busybox', 'lspci'])
    return len(res.splitlines())

  @InfoProperty
  def device_id(self):
    """Returns the device ID of the device."""
    return self._device.ReadFile(session.DEVICE_ID_PATH).strip()

  @InfoProperty
  def device_name(self):
    """Returns the device name of the device."""
    return self._device.CallOutput(['cros_config', '/', 'name']).strip()


def main():
  import pprint
  from cros.factory.device import device_utils
  logging.basicConfig()
  info = SystemInfo(device_utils.CreateDUTInterface())
  pprint.pprint(info.GetAll())


if __name__ == '__main__':
  main()
