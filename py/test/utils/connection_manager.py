# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import glob
import logging
import os
import subprocess
import time

# Import WLAN into this module's namespace, since it may be used by
# some test lists.
from cros.factory.utils import config_utils
from cros.factory.utils import net_utils
from cros.factory.utils.net_utils import WLAN  # pylint: disable=unused-import
from cros.factory.utils import type_utils

try:
  # This import is not a hard dependency.
  from cros.factory.goofy.plugins import plugin_controller
  _HAS_PLUGIN_CONTROLLER = True
except ImportError:
  _HAS_PLUGIN_CONTROLLER = False

try:
  # pylint: disable=unused-import, wrong-import-order
  from cros.factory.test.utils import flimflam_test_path
  import dbus
  import flimflam
except ImportError:
  # E.g., in chroot
  pass

_CONNECTION_TIMEOUT_SECS = 15.0
_PING_TIMEOUT_SECS = 15
_SLEEP_INTERVAL_SECS = 0.5
_SCAN_INTERVAL_SECS = 10

# The dependency of network manager in current ChromeOS is:
#    wpasupplicant +-> shill -> shill_respawn
#                  \-> modemmanager
# So the right order to stop network is:
#    shill_respawn -> shill -> wpasupplicant.
#              modemmanager /

_UNKNOWN_PROC = 'unknown'
_DEFAULT_MANAGER = 'shill'
_DEFAULT_PROC_NAME = 'shill'
_MANAGER_LIST = ['flimflam', 'shill']
_PROC_NAME_LIST = [_UNKNOWN_PROC, 'flimflamd', 'shill']
_DEPSERVICE_LIST = ['wpasupplicant']
_SUBSERVICE_LIST = ['shill_respawn', 'modemmanager']

# %s is the network manager process name, i.e. flimflam or shill.
_PROFILE_LOCATION = '/var/cache/%s/default.profile'


def GetConnectionManagerProxy():
  proxy = None
  if _HAS_PLUGIN_CONTROLLER:
    proxy = plugin_controller.GetPluginRPCProxy('connection_manager')
  if proxy is None:
    logging.info('Goofy plugin connection_manager is not running, '
                 'create our own instance')
    proxy = ConnectionManager()
  return proxy


class ConnectionManagerException(Exception):
  ErrorCode = type_utils.Enum([
      # shill does not start a service for a device without physical link
      'NO_PHYSICAL_LINK',
      'INTERFACE_NOT_FOUND',
      # there is no service running on that device
      'NO_SELECTED_SERVICE',
      'NOT_SPECIFIED', ])

  def __init__(self, message, error_code=ErrorCode.NOT_SPECIFIED):
    super(ConnectionManagerException, self).__init__(message)
    self.error_code = error_code
    self.message = message


def GetBaseNetworkManager():
  """Wrapper function of the base network manager constructor.

  The function returns an object of the real underlying ChromeOS network
  manager (flimflam/shill). Although we are actually using shill right now,
  the naming in the Python interface has not been changed yet and we still
  need to use the flimflam module as the interface. The wrapping is to
  facilitate the writing of unit test and to simplify the migration to the shill
  later. Please note that this is different from the network_manager parameter
  used in the ConnectionManager and is determined only by the Python interface
  provided the OS.

  You can find exposed DBUS API from:
    https://chromium.googlesource.com/aosp/platform/system/connectivity/shill/+/HEAD/doc/
  """
  return flimflam.FlimFlam()


class ConnectionManager:

  def __init__(self, wlans=None, scan_interval=_SCAN_INTERVAL_SECS,
               network_manager=_DEFAULT_MANAGER,
               process_name=_DEFAULT_PROC_NAME,
               start_enabled=True,
               depservices=None,
               subservices=None,
               profile_path=_PROFILE_LOCATION,
               override_blocklisted_devices=None):
    """Constructor.

    Args:
      wlans: A list of preferred wireless networks and their properties.
          Each item should be a WLAN object.
      scan_interval: The desired interval between each wireless network scanning
          in seconds. Setting this value to 0 disables periodic scanning.
      network_manager: The name of the network manager in initctl. It
          should be either flimflam(old) or shill(new).
      process_name: The name of the network manager process, which should be
          flimflamd or shill. If you are not sure about it, you can use
          _UNKNOWN_PROC to let the class auto-detect it.
      start_enabled: Whether networking should start enabled.
      depservices: The list of networking-related system services that flimflam/
          shill depends on.
      subservices: The list of networking-related system services other than
          flimflam/shill and their dependency.
      profile_path: The file path of the network profile used by flimflam/shill.
      override_blocklisted_devices: blocklist to override shill's default
          settings.  Should be a list of strings (like ['eth0', 'wlan0']), an
          empty list or empty string (block nothing), or None (don't override).
    """
    if depservices is None:
      depservices = _DEPSERVICE_LIST
    if subservices is None:
      subservices = _SUBSERVICE_LIST
    # Black hole for those useless outputs.
    self.fnull = open(os.devnull, 'w')

    assert network_manager in _MANAGER_LIST
    assert process_name in _PROC_NAME_LIST
    assert scan_interval >= 0
    self.network_manager = network_manager
    self.process_name = process_name
    self.scan_interval = scan_interval
    self.depservices = depservices
    self.subservices = subservices
    self.profile_path = profile_path
    self.override_blocklisted_devices = override_blocklisted_devices
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
      if override_blocklisted_devices is None:
        self.EnableNetworking(reset=False)
      else:
        self.EnableNetworking(reset=True)
    else:
      self.DisableNetworking(clear=False)

  def _DetectProcName(self):
    """Tries to auto-detect the network manager process name."""
    # Try to detects the network manager process with pgrep.
    for process_name in _PROC_NAME_LIST[1:]:
      if not subprocess.call('pgrep %s' % process_name,
                             shell=True, stdout=self.fnull):
        self.process_name = process_name
        return
    raise ConnectionManagerException("Can't find the network manager process")

  def _GetInterfaces(self):
    """Gets the list of all network interfaces."""
    device_paths = glob.glob('/sys/class/net/*')
    interfaces = [os.path.basename(x) for x in device_paths]
    try:
      interfaces.remove('lo')
    except ValueError:
      logging.info('Local loopback is not found. Skipped')
    return interfaces

  def _ConfigureWifi(self, wlans):
    """Configures the wireless network settings.

    The setting will let the network manager auto-connect the preferred
    wireless networks.

    Args:
      wlans: A list of preferred wireless networks and their properties.
          Each item should be a WLAN object.
    """
    for wlan in wlans:
      wlan_dict = {
          'Type': 'wifi',
          'Mode': 'managed',
          'AutoConnect': True,
          'SSID': wlan.ssid,
          'SecurityClass': wlan.security
      }
      # "Passphrase" is only needed for secure wifi.
      if wlan.security != 'none':
        wlan_dict.update({
            'Passphrase': wlan.passphrase
        })
      self.wlans.append(wlan_dict)

  def SetStaticIP(self, interface_or_path, address, prefixlen=None,
                  gateway=None, mtu=None, name_servers=None):
    """Tells underlying connection manager to use static IP on an interface.

    Args:
      interface_or_path: name of the interface (eth0, lan0, ...) or the realpath
        of /sys/class/net/<device> (should looks like:
        /sys/devices/pci0000:00/...)
      address: IP address to set  (string), None to unset
      prefixlen: IP prefix length  (int), None to unset
      gateway: network gateway  (string), None to unset
      mtu: maximum transmission unit  (int), None to unset
      name_servers: list of name servers  (strings), None to unset

    Raises:
      ConnectionManagerException: Will raise ConnectionManagerException if we
        cannot config static IP by shill, the caller can try to config static IP
        by themselves (e.g.  net_utils.SetEthernetIp(...))
      DBusException: Exceptions raised from dbus operation.
    """
    try:
      base_manager = GetBaseNetworkManager()
    except dbus.exceptions.DBusException:
      logging.exception('Could not find the network manager service')
      raise

    interface = net_utils.GetNetworkInterfaceByPath(interface_or_path)
    device = base_manager.FindElementByNameSubstring('Device', interface)

    if device is None:  # Cannot find it.
      raise ConnectionManagerException(
          'Cannot find interface %s' % interface,
          error_code=ConnectionManagerException.ErrorCode.INTERFACE_NOT_FOUND)

    device.Enable()  # Try to enable the device.
    device_props = device.GetProperties()
    if not device_props.get('Ethernet.LinkUp', False):
      # There is no physical link.
      raise ConnectionManagerException(
          'No physical link presents on interface %s' % interface,
          error_code=ConnectionManagerException.ErrorCode.NO_PHYSICAL_LINK)

    service_path = device_props['SelectedService']
    if service_path == '/':
      raise ConnectionManagerException(
          'No service running on interface %s' % interface,
          error_code=ConnectionManagerException.ErrorCode.NO_SELECTED_SERVICE)

    service = base_manager.FindElementByNameSubstring('Service', service_path)

    config = dbus.Dictionary({}, signature='sv')
    if address is not None:
      config['Address'] = dbus.String(address)
    if prefixlen is not None:
      config['Prefixlen'] = dbus.Int32(prefixlen)
    if gateway is not None:
      config['Gateway'] = dbus.String(gateway)
    if mtu is not None:
      config['Mtu'] = dbus.Int32(mtu)
    if name_servers is not None:
      if isinstance(name_servers, str):
        name_servers = [name_servers]
      config['NameServers'] = dbus.Array(name_servers, signature='s')

    service.SetProperty('StaticIPConfig', config)

    # Need to disable / enable device to make it work.
    device.Disable()
    device.Enable()

  def EnableNetworking(self, reset=True):
    """Tells underlying connection manager to try auto-connecting.

    Args:
      reset: Force a clean restart of the network services. Remove previous
          states if there is any.
    """
    if reset:
      # Make sure the network services are really stopped.
      self.DisableNetworking()

    logging.info('Enabling networking')

    # Turn on drivers for interfaces.
    for dev in self._GetInterfaces():
      logging.info('ifconfig %s up', dev)
      subprocess.call('ifconfig %s up' % dev, shell=True, stdout=self.fnull,
                      stderr=self.fnull)

    # Start network manager.
    for service in self.depservices + [self.network_manager] + self.subservices:
      cmd = 'start %s' % service
      if (service in _MANAGER_LIST and
          self.override_blocklisted_devices is not None):
        cmd += ' BLOCKED_DEVICES="%s"' % (
            ','.join(self.override_blocklisted_devices))
      logging.info('Call cmd: %s', cmd)
      subprocess.call(cmd, shell=True, stdout=self.fnull, stderr=self.fnull)

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
        base_manager.manager.ConfigureService(wlan, signature='a{sv}')
      except dbus.exceptions.DBusException:
        logging.exception('Unable to configure wireless network: %s',
                          wlan['SSID'])
    return True

  def DisableNetworking(self, clear=True):
    """Tells underlying connection manager to terminate any existing connection.

    Args:
      clear: clear configured profiles related to services.
    """
    logging.info('Disabling networking')

    # Stop network manager.
    for service in self.subservices + [self.network_manager] + self.depservices:
      subprocess.call('stop %s' % service, shell=True,
                      stdout=self.fnull, stderr=self.fnull)

    # Turn down drivers for interfaces to really stop the network.
    for dev in self._GetInterfaces():
      subprocess.call('ifconfig %s down' % dev, shell=True, stdout=self.fnull,
                      stderr=self.fnull)

    # Delete the configured profiles
    if clear:
      try:
        os.remove(self.profile_path % self.process_name)
      except OSError:
        logging.exception('Unable to remove the network profile.'
                          ' File non-existent?')

  def WaitForConnection(self, timeout=_CONNECTION_TIMEOUT_SECS):
    """A blocking function that waits until any network is connected.

    The function will raise an Exception if no network is ready when
    the time runs out.

    Args:
      timeout: Timeout in seconds.
    """
    t_start = time.clock()
    while not self.IsConnected():
      if time.clock() - t_start > timeout:
        raise ConnectionManagerException('Not connected')
      time.sleep(_SLEEP_INTERVAL_SECS)

  def IsConnected(self):
    """Returns (network state == online)."""
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


def PingHost(host, timeout=_PING_TIMEOUT_SECS):
  """Checks if we can reach a host.

  Args:
    host: The host address.
    timeout: Timeout in seconds. Integers only.

  Returns:
    True if host is successfully pinged.
  """
  with open(os.devnull, 'w') as fnull:
    return subprocess.call(
        'ping %s -c 1 -w %d' % (host, int(timeout)),
        shell=True, stdout=fnull, stderr=fnull)


def LoadNetworkConfig(config_name):
  """Load network config ``config_name``.

  The schema file is ``./network_config.schema.json``.

  Args:
    config_name: config file name with or without extension (".json").  If the
      file name is given in relative path, default directory will be *this*
      directory (test/utils/).  Absolute path is also allowed.
  Returns:
    dict object, the content of config file.
  """
  if config_name.endswith(config_utils.CONFIG_FILE_EXT):
    config_name = config_name[:-len(config_utils.CONFIG_FILE_EXT)]
  return config_utils.LoadConfig(config_name=config_name,
                                 schema_name='network_config')


def SetupNetworkUsingNetworkConfig(network_config):
  """Setup network interfaces using ``ConnectionManager``.

  Args:
    network_config: a dict object which is compatible with
      ``network_config.schema.json`` (you can load a config file using
      ``LoadNetworkConfig``)
  """
  proxy = GetConnectionManagerProxy()

  def _SetStaticIP(*args, **kwargs):
    try:
      return proxy.SetStaticIP(*args, **kwargs)
    except ConnectionManagerException as e:
      # if proxy is actually a connection manager instance, error code is raised
      # as an exception, rather than return value.
      return e.error_code

  for interface in network_config:
    interface_name = network_config[interface].pop('interface_name', interface)
    error_code = _SetStaticIP(interface_or_path=interface,
                              **network_config[interface])
    if error_code:
      logging.error('failed to setup interface %s: %s',
                    interface_name, error_code)


def main():
  parser = argparse.ArgumentParser(
      description='setup network interfaces by config file')

  parser.add_argument('--config_path', '-c', help='path to config file',
                      required=True)

  options = parser.parse_args()
  network_config = LoadNetworkConfig(os.path.abspath(options.config_path))
  SetupNetworkUsingNetworkConfig(network_config)


if __name__ == '__main__':
  main()
