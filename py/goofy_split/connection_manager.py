# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os
import subprocess
import time

try:
  from cros.factory.goofy import flimflam_test_path  # pylint: disable=W0611
  import dbus  # pylint: disable=F0401
  import flimflam  # pylint: disable=F0401
except ImportError:
  # E.g., in chroot
  pass

_CONNECTION_TIMEOUT_SECS = 15.0
_PING_TIMEOUT_SECS = 15
_SLEEP_INTERVAL_SECS = 0.5
_SCAN_INTERVAL_SECS = 10

_UNKNOWN_PROC = 'unknown'
_DEFAULT_MANAGER = 'shill'
_DEFAULT_PROC_NAME = 'shill'
_MANAGER_LIST = ['flimflam', 'shill']
_PROC_NAME_LIST = [_UNKNOWN_PROC, 'flimflamd', 'shill']
_SUBSERVICE_LIST = ['shill_respawn', 'wpasupplicant', 'modemmanager']

# %s is the network manager process name, i.e. flimflam or shill.
_PROFILE_LOCATION = '/var/cache/%s/default.profile'


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
        instead of "wpa". Using "wpa" will result in an explicit exception.
      passphrase: Wireless network password.
    '''
    if security == 'wpa':
      raise ConnectionManagerException("Invalid wireless network security type:"
                                       " wpa. Use 'psk' instead")
    if not security in ['none', 'wep', 'rsn', 'psk', '802_1x']:
      raise ConnectionManagerException("Invalid wireless network security type:"
                                       " %s" % security)
    self.ssid = ssid
    self.security = security
    self.passphrase = passphrase


def GetBaseNetworkManager():
  ''' Wrapper function of the base network manager constructor.

  The function returns an object of the real underlying ChromeOS network
  manager (flimflam/shill). Although we are actually using shill right now,
  the naming in the Python interface has not been changed yet and we still
  need to use the flimflam module as the interface. The wrapping is to
  facilitate the writing of unit test and to simplify the migration to the shill
  later. Please note that this is different from the network_manager parameter
  used in the ConnectionManager and is determined only by the Python interface
  provided the OS.
  '''
  return flimflam.FlimFlam()


class ConnectionManager():

  def __init__(self, wlans=None, scan_interval=_SCAN_INTERVAL_SECS,
               network_manager=_DEFAULT_MANAGER,
               process_name=_DEFAULT_PROC_NAME,
               start_enabled=True,
               subservices=list(_SUBSERVICE_LIST),
               profile_path=_PROFILE_LOCATION):
    '''Constructor.

    Args:
      wlans: A list of preferred wireless networks and their properties.
             Each item should be a WLAN object.
      scan_interval: The desired interval between each wireless network scanning
                     in seconds. Setting this value to 0 disables periodic
                     scanning.
      network_manager: The name of the network manager in initctl. It
                       should be either flimflam(old) or shill(new).
      process_name: The name of the network manager process, which should be
                    flimflamd or shill. If you are not sure about it, you can
                    use _UNKNOWN_PROC to let the class auto-detect it.
      start_enabled: Whether networking should start enabled.
      subservices: The list of networking-related system services other than
                   flimflam/shill.
      profile_path: The file path of the network profile used by flimflam/shill.
    '''
    # Black hole for those useless outputs.
    self.fnull = open(os.devnull, 'w')

    assert network_manager in _MANAGER_LIST
    assert process_name in _PROC_NAME_LIST
    assert scan_interval >= 0
    self.network_manager = network_manager
    self.process_name = process_name
    self.scan_interval = scan_interval
    self.subservices = subservices
    self.profile_path = profile_path
    # Auto-detect the network manager process name if unknown.
    if self.process_name == _UNKNOWN_PROC:
      self._DetectProcName()
    if wlans is None:
      wlans = []
    self.wlans = []
    self._ConfigureWifi(wlans)

    logging.info('Created connection manager: wlans=[%s]',
                 ', '.join([x['SSID'] for x in self.wlans]))

    if start_enabled:
      self.EnableNetworking(reset=False)
    else:
      self.DisableNetworking(clear=False)

  def _DetectProcName(self):
    '''Tries to auto-detect the network manager process name.'''
    # Try to detects the network manager process with pgrep.
    for process_name in _PROC_NAME_LIST[1:]:
      if not subprocess.call("pgrep %s" % process_name,
                             shell=True, stdout=self.fnull):
        self.process_name = process_name
        return
    raise ConnectionManagerException("Can't find the network manager process")

  def _GetInterfaces(self):
    '''Gets the list of all network interfaces.'''
    device_paths = glob.glob('/sys/class/net/*')
    interfaces = [os.path.basename(x) for x in device_paths]
    try:
      interfaces.remove('lo')
    except ValueError:
      logging.info('Local loopback is not found. Skipped')
    return interfaces

  def _ConfigureWifi(self, wlans):
    '''Configures the wireless network settings.

    The setting will let the network manager auto-connect the preferred
    wireless networks.

    Args:
      wlans: A list of preferred wireless networks and their properties.
             Each item should be a WLAN object.
    '''
    for wlan in wlans:
      wlan_dict = {
        'Type': 'wifi',
        'Mode': 'managed',
        'AutoConnect': True,
        'SSID': wlan.ssid,
        'Security': wlan.security
      }
      # "Passphrase" is only needed for secure wifi.
      if wlan.security is not "none":
        wlan_dict.update({
          'Passphrase': wlan.passphrase
        })
      self.wlans.append(wlan_dict)

  def EnableNetworking(self, reset=True):
    '''Tells underlying connection manager to try auto-connecting.

    Args:
      reset: Force a clean restart of the network services. Remove previous
             states if there is any.
    '''
    if reset:
      # Make sure the network services are really stopped.
      self.DisableNetworking()

    logging.info('Enabling networking')

    # Turn on drivers for interfaces.
    for dev in self._GetInterfaces():
      logging.info('ifconfig %s up', dev)
      subprocess.call("ifconfig %s up" % dev, shell=True, stdout=self.fnull,
                      stderr=self.fnull)

    # Start network manager.
    for service in [self.network_manager] + self.subservices:
      subprocess.call("start %s" % service, shell=True,
                      stdout=self.fnull, stderr=self.fnull)

    # Configure the network manager to auto-connect wireless networks.
    try:
      base_manager = GetBaseNetworkManager()
    except dbus.exceptions.DBusException:
      logging.exception('Could not find the network manager service')
      return False

    # Configure the wireless network scanning interval.
    for dev in self._GetInterfaces():
      if 'wlan' in dev or 'mlan' in dev:
        try:
          device = base_manager.FindElementByNameSubstring('Device', dev)
          device.SetProperty('ScanInterval', dbus.UInt16(self.scan_interval))
        except dbus.exceptions.DBusException:
          logging.exception('Failed to set scanning interval for interface: %s',
                            dev)
        except AttributeError:
          logging.exception('Unable to find the interface: %s', dev)

    # Set the known wireless networks.
    for wlan in self.wlans:
      try:
        base_manager.manager.ConfigureService(wlan)
      except dbus.exceptions.DBusException:
        logging.exception('Unable to configure wireless network: %s',
                          wlan['SSID'])
    return True

  def DisableNetworking(self, clear=True):
    '''Tells underlying connection manager to terminate any existing connection.

    Args:
      clear: clear configured profiles related to services.
    '''
    logging.info('Disabling networking')

    # Stop network manager.
    for service in self.subservices + [self.network_manager]:
      subprocess.call("stop %s" % service, shell=True,
                      stdout=self.fnull, stderr=self.fnull)

    # Turn down drivers for interfaces to really stop the network.
    for dev in self._GetInterfaces():
      subprocess.call("ifconfig %s down" % dev, shell=True, stdout=self.fnull,
                      stderr=self.fnull)

    # Delete the configured profiles
    if clear:
      try:
        os.remove(self.profile_path % self.process_name)
      except OSError:
        logging.exception("Unable to remove the network profile."
                          " File non-existent?")

  def WaitForConnection(self, timeout=_CONNECTION_TIMEOUT_SECS):
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
      time.sleep(_SLEEP_INTERVAL_SECS)

  def IsConnected(self):
    '''Returns (network state == online).'''
    # Check if we are connected to any network.
    # We can't cache the flimflam object because each time we re-start
    # the network some filepaths that flimflam works on will change.
    try:
      base_manager = GetBaseNetworkManager()
    except dbus.exceptions.DBusException:
      # The network manager is not running.
      return False

    stat = base_manager.GetSystemState()
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

  def WaitForConnection(self, timeout=_CONNECTION_TIMEOUT_SECS):
    pass

  def IsConnected(self):
    return True

def PingHost(host, timeout=_PING_TIMEOUT_SECS):
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
