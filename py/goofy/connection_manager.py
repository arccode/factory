# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import dbus
import httplib
import logging
import os
import re
import subprocess
import sys
import time

try:
  from cros.factory.goofy import flimflam_test_path
  import flimflam
except ImportError:
  # E.g., in chroot
  pass

_CONNECTION_TIMEOUT_SEC = 15.0
_PING_TIMEOUT_SEC = 15
_SLEEP_INTERVAL_SEC = 0.5

_UNKNOWN_PROC = 'unknown'
_DEFAULT_MANAGER = 'flimflam'
_DEFAULT_PROC_NAME = _UNKNOWN_PROC
_MANAGER_LIST = ['flimflam', 'shill']
_PROC_NAME_LIST = [_UNKNOWN_PROC, 'flimflamd', 'shill']
_SUBSERVICE_LIST = ['flimflam_respawn', 'wpasupplicant', 'modemmanager']


class ConnectionManagerException(Exception):
  pass


class WLAN(object):
  '''Class for wireless network settings.'''
  def __init__(self, ssid, security, passphrase):
    ''' Constructor.

    Please see 'http://code.google.com/searchframe#wZuuyuB8jKQ/src/third_party/
    flimflam/doc/service-api.txt' for a detailed explanation of these
    parameters.

    Args:
      ssid: Wireless network SSID.
      security: Wireless network security type. For example:
        "none": no security.
        "wep": fixed key WEP.
        "wpa": WPA-PSK (but see below; use "psk" instead).
        "rsn": IEEE 802.11i-PSK
        "psk": WPA2-PSK[AES], WPA-PSK[TKIP] + WPA2-PSK[AES].
               Also, "wpa" and "rsn" can be replaced by "psk".
        "802_1x": IEEE 802.11i with 802.1x authentication.

        Note that when using "wpa" for WPA2-PSK[AES] or
        WPA-PSK[TKIP] + WPA2-PSK[AES], flimflam can connect but it will always
        cache the first passphrase that works. For this reason, use "psk"
        instead of "wpa".
      passphrase: Wireless network password.
    '''
    self.ssid = ssid
    self.security = security
    self.passphrase = passphrase


class ConnectionManager():

  def __init__(self, wlans=None,
               network_manager=_DEFAULT_MANAGER,
               process_name=_DEFAULT_PROC_NAME,
               start_enabled=True):
    '''Constructor.

    Args:
      wlans: A list of preferred wireless networks and their properties.
             Each item should be a WLAN object.
      network_manager: The name of the network manager in initctl. It
                       should be either flimflam(old) or shill(new).
      process_name: The name of the network manager process, which should be
                    flimflamd or shill. If you are not sure about it, you can
                    use _UNKNOWN_PROC to let the class auto-detect it.
      start_enabled: Whether networking should start enabled.
    '''
    # Black hole for those useless outputs.
    self.fnull = open(os.devnull, 'w')

    assert network_manager in _MANAGER_LIST
    assert process_name in _PROC_NAME_LIST
    self.network_manager = network_manager
    self.process_name = process_name
    # Auto-detect the network manager process name if unknown.
    if self.process_name == _UNKNOWN_PROC:
      self._DetectProcName()
    if wlans is None:
      wlans = []
    self._ConfigureWifi(wlans)

    # Start network manager to get device info.
    self.EnableNetworking()
    self._GetDeviceInfo()
    if not start_enabled:
      self.DisableNetworking()

  def _DetectProcName(self):
    '''Detects the network manager process with pgrep.'''
    for process_name in _PROC_NAME_LIST[1:]:
      if not subprocess.call("pgrep %s" % process_name,
                             shell=True, stdout=self.fnull):
        self.process_name = process_name
        return
    raise ConnectionManagerException("Can't find the network manager process")

  def _GetDeviceInfo(self):
    '''Gets hardware properties of all network devices.'''
    flim = flimflam.FlimFlam()
    self.device_list = [dev.GetProperties(utf8_strings=True)
                        for dev in flim.GetObjectList("Device")]

  def _ConfigureWifi(self, wlans):
    '''Configures the wireless network settings.

    The setting will let the network manager auto-connect the preferred
    wireless networks.

    Args:
      wlans: A list of preferred wireless networks and their properties.
             Each item should be a WLAN object.
    '''
    self.wlans = []
    for wlan in wlans:
      self.wlans.append({
        'Type': 'wifi',
        'Mode': 'managed',
        'AutoConnect': True,
        'SSID': wlan.ssid,
        'Security': wlan.security,
        'Passphrase': wlan.passphrase
      })

  def EnableNetworking(self):
    '''Tells underlying connection manager to try auto-connecting.'''
    # Start network manager.
    for service in [self.network_manager] + _SUBSERVICE_LIST:
      subprocess.call("start %s" % service, shell=True,
                      stdout=self.fnull, stderr=self.fnull)

    # Configure the network manager to auto-connect wireless networks.
    flim = flimflam.FlimFlam()
    for wlan in self.wlans:
      flim.manager.ConfigureService(wlan)

  def DisableNetworking(self):
    '''Tells underlying connection manager to terminate any existing connection.
    '''
    # Stop network manager.
    for service in _SUBSERVICE_LIST + [self.network_manager]:
      subprocess.call("stop %s" % service, shell=True,
                      stdout=self.fnull, stderr=self.fnull)

    # Turn down drivers for interfaces to really stop the network.
    for dev in self.device_list:
      subprocess.call("ifconfig %s down" % dev['Interface'],
                      shell=True, stdout=self.fnull, stderr=self.fnull)

  def WaitForConnection(self, timeout=_CONNECTION_TIMEOUT_SEC):
    '''A blocking function that waits until any network is connected.

    The function will raise an Exception if no network is ready when
    the time runs out.

    Args:
      timeout: Timeout in seconds.
    '''
    t_start = time.clock()
    while not self.IsConnected():
      if time.clock() - t_start > timeout:
        raise ConnectionManagerException('Not connected')
      time.sleep(_SLEEP_INTERVAL_SEC)

  def IsConnected(self):
    '''Returns (network state == online).'''
    # Check if we are connected to any network.
    # We can't cache the flimflam object because each time we re-start
    # the network some filepaths that flimflam works on will change.
    try:
      flim = flimflam.FlimFlam()
    except dbus.exceptions.DBusException:
      # The network manager is not running.
      return False

    stat = flim.GetSystemState()
    return stat != 'offline'


class DummyConnectionManager(object):
  '''A dummy connection manager that always reports being connected.

  Useful, e.g., in the chroot.'''
  def __init__(self):
    pass

  def DisableNetworking(self):
    logging.warn('DisableNetworking: no network manager is set')

  def EnableNetworking(self):
    logging.warn('EnableNetworking: no network manager is set')

  def WaitForConnection(self, timeout=_CONNECTION_TIMEOUT_SEC):
    pass

  def IsConnected(self):
    return True

def PingHost(host, timeout=_PING_TIMEOUT_SEC):
  '''Checks if we can reach a host.

  Args:
    host: The host address.
    timeout: Timeout in seconds. Integers only.

  Returns:
    True if host is successfully pinged.
  '''
  with open(os.devnull, "w") as fnull:
    return subprocess.call(
      "ping %s -c 1 -w %d" % (host, int(timeout)),
      shell=True, stdout=fnull, stderr=fnull)
