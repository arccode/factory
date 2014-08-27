# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Interfaces to set and get system status and system information."""


import collections
import glob
import logging
import netifaces
import os
import re
import subprocess
import threading

import factory_common  # pylint: disable=W0611
from cros.factory import hwid
from cros.factory.system import partitions
from cros.factory.system.board import Board
from cros.factory import test
from cros.factory.test import factory
from cros.factory.test.utils import ReadOneLine
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountDeviceAndReadFile

# pylint: disable=W0702
# Disable checking of exception types, since we catch all exceptions
# in many places.

_board = None
_lock = threading.Lock()


def GetBoard():
  """Returns a board instance for the device under test.

  By default, a
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard` object
  is returned, but this may be overridden by setting the
  ``CROS_FACTORY_BOARD_CLASS`` environment variable in
  ``board_setup_factory.sh``.  See :ref:`board-api-extending`.

  Returns:
    An instance of the specified Board class implementation.
  """
  # pylint: disable=W0603
  with _lock:
    global _board
    if _board:
      return _board

    board = os.environ.get('CROS_FACTORY_BOARD_CLASS',
                           'cros.factory.board.chromeos_board.ChromeOSBoard')
    module, cls = board.rsplit('.', 1)
    _board = getattr(__import__(module, fromlist=[cls]), cls)()
    return _board


class SystemInfo(object):
  """Static information about the system.

  This is mostly static information that changes rarely if ever
  (e.g., version numbers, serial numbers, etc.).
  """
  # If not None, an update that is available from the update server.
  update_md5sum = None

  # The cached release image version.
  release_image_version = None

  def __init__(self):
    self.mlb_serial_number = None
    try:
      self.mlb_serial_number = test.shopfloor.GetDeviceData()[
          'mlb_serial_number']
    except:
      pass

    self.serial_number = None
    try:
      self.serial_number = test.shopfloor.get_serial_number()
      if self.serial_number is not None:
        self.serial_number = str(self.serial_number)
    except:
      pass

    self.stage = None
    try:
      self.stage = test.shopfloor.GetDeviceData()['stage']
    except:
      pass

    self.factory_image_version = None
    try:
      lsb_release = open('/etc/lsb-release').read()
      match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release,
                        re.MULTILINE)
      if match:
        self.factory_image_version = match.group(1)
    except:
      pass

    self.toolkit_version = None
    try:
      with open('/usr/local/factory/TOOLKIT_VERSION') as f:
        self.toolkit_version = f.read().strip()
    except:
      pass

    self.release_image_version = None
    try:
      if SystemInfo.release_image_version:
        self.release_image_version = SystemInfo.release_image_version
        logging.debug('Obtained release image version from SystemInfo: %r',
                      self.release_image_version)
      else:
        release_rootfs = partitions.RELEASE_ROOTFS.path
        lsb_release = MountDeviceAndReadFile(release_rootfs, '/etc/lsb-release')
        logging.debug('Release image version does not exist in SystemInfo. '
                      'Try to get it from lsb-release from release partition.')

        match = re.search('^GOOGLE_RELEASE=(.+)$', lsb_release, re.MULTILINE)
        if match:
          self.release_image_version = match.group(1)
          logging.debug('release image version: %s',
                        self.release_image_version)
          logging.debug('Cache release image version to SystemInfo.')
          SystemInfo.release_image_version = self.release_image_version
        else:
          logging.debug('Can not read release image version from lsb-release.')

    except:
      pass

    self.wlan0_mac = None
    try:
      for wlan_interface in ['mlan0', 'wlan0']:
        address_path = os.path.join('/sys/class/net/',
                                    wlan_interface, 'address')
        if os.path.exists(address_path):
          self.wlan0_mac = open(address_path).read().strip()
    except:
      pass

    self.eth_macs = dict()
    try:
      eth_paths = glob.glob('/sys/class/net/eth*')
      for eth_path in eth_paths:
        address_path = os.path.join(eth_path, 'address')
        if os.path.exists(address_path):
          self.eth_macs[os.path.basename(eth_path)] = open(
              address_path).read().strip()
    except:
      self.eth_macs = None

    self.kernel_version = None
    try:
      uname = subprocess.Popen(['uname', '-r'], stdout=subprocess.PIPE)
      stdout, _ = uname.communicate()
      self.kernel_version = stdout.strip()
    except:
      pass

    self.architecture = None
    try:
      self.architecture = Spawn(['uname', '-m'],
                                check_output=True).stdout_data.strip()
    except:
      pass

    self.ec_version = None
    try:
      self.ec_version = GetBoard().GetECVersion()
    except:
      pass

    self.pd_version = None
    try:
      self.pd_version = GetBoard().GetPDVersion()
    except:
      pass

    self.firmware_version = None
    try:
      crossystem = subprocess.Popen(['crossystem', 'fwid'],
                                    stdout=subprocess.PIPE)
      stdout, _ = crossystem.communicate()
      self.firmware_version = stdout.strip() or None
    except:
      pass

    self.root_device = None
    try:
      rootdev = Spawn(['rootdev', '-s'],
                      stdout=subprocess.PIPE, ignore_stderr=True)
      stdout, _ = rootdev.communicate()
      self.root_device = stdout.strip()
    except:
      pass

    self.factory_md5sum = factory.get_current_md5sum()

    # Uses checksum of hwid file as hwid database version.
    self.hwid_database_version = None
    try:
      hwid_file_path = os.path.join(hwid.common.DEFAULT_HWID_DATA_PATH,
                                    hwid.common.ProbeBoard().upper())
      if os.path.exists(hwid_file_path):
        self.hwid_database_version = hwid.hwid_utils.ComputeDatabaseChecksum(
            hwid_file_path)
    except:
      pass

    # update_md5sum is currently in SystemInfo's __dict__ but not this
    # object's.  Copy it from SystemInfo into this object's __dict__.
    self.update_md5sum = SystemInfo.update_md5sum


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
    _SysfsAttribute('voltage_min_design', int, False),
    _SysfsAttribute('voltage_now', int, False),
    _SysfsAttribute('energy_full', int, True),
    _SysfsAttribute('energy_full_design', int, True),
    _SysfsAttribute('energy_now', int, True),
]


class SystemStatus(object):
  """Information about the current system status.

  This is information that changes frequently, e.g., load average
  or battery information.

  We log a bunch of system status here.
  """
  # Class variable: a charge_manager instance for checking force
  # charge status.
  charge_manager = None

  def __init__(self):
    def _CalculateBatteryFractionFull(battery):
      for t in ['charge', 'energy']:
        now = battery['%s_now' % t]
        full = battery['%s_full' % t]
        if (now is not None and full is not None and full > 0 and now >= 0):
          return float(now) / full
      return None

    self.battery = {}
    self.battery_sysfs_path = None
    path_list = glob.glob('/sys/class/power_supply/*/type')
    for p in path_list:
      try:
        if open(p).read().strip() == 'Battery':
          self.battery_sysfs_path = os.path.dirname(p)
          break
      except:
        logging.warning('sysfs path %s is unavailable', p)

    for k, item_type, optional in _SysfsBatteryAttributes:
      self.battery[k] = None
      try:
        if self.battery_sysfs_path:
          self.battery[k] = item_type(
              open(os.path.join(self.battery_sysfs_path, k)).read().strip())
      except:
        log_func = logging.error
        if optional:
          log_func = logging.debug
        log_func('sysfs path %s is unavailable',
                 os.path.join(self.battery_sysfs_path, k))

    self.battery['fraction_full'] = _CalculateBatteryFractionFull(self.battery)

    self.battery['force'] = False
    if self.charge_manager:
      force_status = {
          Board.ChargeState.DISCHARGE: 'Discharging',
          Board.ChargeState.CHARGE: 'Charging',
          Board.ChargeState.IDLE: 'Idle'}.get(
              self.charge_manager.state)
      if force_status:
        self.battery['status'] = force_status
        self.battery['force'] = True

    # Get fan speed
    try:
      self.fan_rpm = GetBoard().GetFanRPM()
    except:
      self.fan_rpm = None

    # Get temperatures from sensors
    try:
      self.temperatures = GetBoard().GetTemperatures()
    except:
      self.temperatures = []

    try:
      self.main_temperature_index = GetBoard().GetMainTemperatureIndex()
    except:
      self.main_temperature_index = None

    try:
      self.load_avg = map(
          float, open('/proc/loadavg').read().split()[0:3])
    except:
      self.load_avg = None

    try:
      self.cpu = map(int, open('/proc/stat').readline().split()[1:])
    except:
      self.cpu = None

    try:
      self.ips = GetIPv4Addresses()
    except:
      self.ips = None

    try:
      self.eth_on = IsInterfaceConnected('eth')
    except:
      self.eth_on = None

    try:
      self.wlan_on = (IsInterfaceConnected('mlan') or
                      IsInterfaceConnected('wlan'))
    except:
      self.wlan_on = None

if __name__ == '__main__':
  import yaml
  print yaml.dump(dict(system_info=SystemInfo(None, None).__dict__,
                       system_status=SystemStatus().__dict__),
                  default_flow_style=False)


def SetBacklightBrightness(level):
  """Sets the backlight brightness level.

  Args:
    level: A floating-point value in [0.0, 1.0] indicating the backlight
        brightness level.

  Raises:
    ValueError if the specified value is invalid.
  """
  if not (level >= 0.0 and level <= 1.0):
    raise ValueError('Invalid brightness level.')
  interfaces = glob.glob('/sys/class/backlight/*')
  for i in interfaces:
    with open(os.path.join(i, 'brightness'), 'w') as f:
      f.write('%d' % int(
          level * float(ReadOneLine(os.path.join(i, 'max_brightness')))))
