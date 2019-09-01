#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import re
import threading
import uuid

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.device.bluetooth import BluetoothManager
from cros.factory.device.bluetooth import BluetoothManagerException
from cros.factory.device import device_utils
from cros.factory.utils.sync_utils import PollForCondition
from cros.factory.utils.sync_utils import Retry

from cros.factory.external import dbus
# pylint: disable=no-name-in-module,import-error
from cros.factory.external.dbus import DBusException
from cros.factory.external.dbus.mainloop.glib import DBusGMainLoop
from cros.factory.external.dbus import service  # pylint: disable=unused-import
from cros.factory.external import gobject


BUS_NAME = 'org.bluez'
SERVICE_NAME = 'org.bluez'
ADAPTER_INTERFACE = SERVICE_NAME + '.Adapter1'
DEVICE_INTERFACE = SERVICE_NAME + '.Device1'
AGENT_INTERFACE = SERVICE_NAME + '.Agent1'

_RE_NODE_NAME = re.compile(r'<node name="(.*?)"/>')


class AuthenticationAgent(dbus.service.Object):
  """An authenticator for Bluetooth devices

  This class implements methods from the org.bluez.Agent1 D-Bus
  interface, which allow Bluetooth devices to authenticate themselves
  against the host (the computer running this script). This does not
  implement the full interface; for example it does not support the
  legacy PIN code mechanism used by pre-2.1 Bluetooth keyboards.

  Properties:
    _bus: The device Bus to use
    _path: The object path of the Agent
    _display_passkey_callback: A function with signature (string) that takes
        a 6 digit passkey to display to the user
    _cancel_callback: A function that takes no parameters, used
        to indicate cancellation from the device
  """
  def __init__(self, bus, path, display_passkey_callback, cancel_callback):
    dbus.service.Object.__init__(self, bus, path)
    self._display_passkey_callback = display_passkey_callback
    self._cancel_callback = cancel_callback

  # The following method names and their in/out signatures must match the
  # corresponding methods in the BlueZ 5 Agent1 DBus interface, including the
  # types of the parameters. The signature 'ouq' indicates that we take three
  # parameters (excluding self), of type Object, uint32, uint16 respectively
  # (note that 'q' is NOT a quadword like you might expect). Of course, in
  # Python, they're just arbitrary precision integers, but the signature
  # must still match for the method to be properly called.
  @dbus.service.method(AGENT_INTERFACE, in_signature='ouq', out_signature='')
  def DisplayPasskey(self, device, passkey, entered):
    logging.info('DisplayPasskey (%s, %06u entered %u)',
                 device, passkey, entered)
    # passkey is always 6 digits, so add any leading 0s
    passkey_str = str(passkey).zfill(6)
    self._display_passkey_callback(passkey_str)

  @dbus.service.method(AGENT_INTERFACE, in_signature='', out_signature='')
  def Cancel(self):
    logging.info('Cancel')
    self._cancel_callback()


# TODO(cychiang) Add unittest for this class.
class ChromeOSBluetoothManager(BluetoothManager):
  """The class to handle bluetooth adapter and device through dbus interface.

  Properties:
    _main_loop: The object representing the main event loop of a PyGTK
        or PyGObject application. The main loop should be running
        when calling function with callback through dbus interface.
    _manager: The proxy for the org.freedesktoop.DBus.ObjectManager interface
        on ojbect path / on bus org.bluez.

  Raises:
    Raises BluetoothManagerException if org.bluez.Manager object is not
    available through dbus interface.
  """

  Error = BluetoothManagerException

  def __init__(self, dut):
    super(ChromeOSBluetoothManager, self).__init__(dut)
    DBusGMainLoop(set_as_default=True)
    self._main_loop = gobject.MainLoop()
    self._manager = None
    bus = dbus.SystemBus()
    try:
      self._manager = dbus.Interface(bus.get_object(BUS_NAME, '/'),
                                     'org.freedesktop.DBus.ObjectManager')
    except DBusException as e:
      raise BluetoothManagerException('DBus Exception in getting Manager'
                                      'dbus Interface: %s.' % e)

  def _FindDeviceInterface(self, mac_addr, adapter):
    """Given a MAC address, returns the corresponding device dbus object

    Args:
      mac_addr: The MAC address of the remote device
      adapter: The bluetooth adapter dbus interface object
    """
    # Remote devices belonging to the given adapter
    # have their path prefixed by the adapter's object path
    path_prefix = adapter.object_path
    bus = dbus.SystemBus()
    remote_objects = self._manager.GetManagedObjects()
    for path, ifaces in remote_objects.iteritems():
      if path.startswith(path_prefix):
        device = ifaces.get(DEVICE_INTERFACE)
        if device and str(device['Address']) == mac_addr:
          matching_device = bus.get_object(SERVICE_NAME, path)
          return dbus.Interface(matching_device, DEVICE_INTERFACE)
    return None

  def SetDeviceConnected(self, adapter, device_address, connect):
    """Switches the device connection.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.
      connect: True/False to turn on/off the connection.

    Returns:
      Return True if succeed to turn on/off connection.

    Raises:
      Raises BluetoothManagerException if fail to find device or fail to switch
      connection.
    """
    try:
      device = self._FindDeviceInterface(device_address, adapter)
    except DBusException as e:
      raise BluetoothManagerException('SetDeviceConnected: fail to find device'
                                      ' %s: %s' % (device_address, e))
    try:
      if connect:
        device.Connect()
      else:
        # If we could not find the device, then we are not connected to it
        if device:
          device.Disconnect()
    except DBusException as e:
      raise BluetoothManagerException('SetDeviceConnected: fail to switch'
                                      'connection: %s' % e)
    else:
      return True

  def RemovePairedDevice(self, adapter, device_address):
    """Removes the paired device.

    Note that a removed device may not be found in subsequent scans
    for a period of time.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.

    Returns:
      Return True if succeed to remove paired device.

    Raises:
      Raises BluetoothManagerException if fail to remove paired device.
    """
    try:
      device = self._FindDeviceInterface(device_address, adapter)
      if device:
        adapter.RemoveDevice(device)
    except DBusException as e:
      raise BluetoothManagerException('RemovePairedDevice: fail to remove'
                                      ' device: %s.' % e)
    else:
      logging.info('succesfully removed device.')
      return True

  def DisconnectAndUnpairDevice(self, adapter, device_address):
    """Disconnects and unpairs from the device, even if not currently paired.

    This is intended to restore Bluetooth connection status to a known state.
    DBus raises exceptions if not currently paired, so we swallow those.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.

    Returns: Nothing
    """
    device = self._FindDeviceInterface(device_address, adapter)
    if device:
      try:
        device.Disconnect()
      except DBusException:
        pass
      try:
        device.CancelPairing()
      except DBusException:
        pass

  def CreatePairedDevice(self, adapter, device_address,
                         display_passkey_callback=None,
                         cancel_callback=None):
    """Create paired device.

    Attempt to pair with a Bluetooth device, making the computer running this
    script the host. If a callback is specified for displaying a passkey, this
    host will report KeyboardDisplay capabilities, allowing the remote device
    (which must be a keyboard) to respond with a passkey which must be typed on
    it to authenticate. If the callback is not specified, the host reports no
    interactive capabilities, forcing a "Just Works" pairing model (that's the
    actual name in the Bluetooth spec) that pairs with no authentication.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.
      display_passkey_callback: None, or a function with signature (string)
        that is passed a passkey for authentication
      cancel_callback: None, or a function that accepts no arguments that is
        invoked if the remote device cancels authentication

    Raises:
      Raises BluetoothManagerException if fails to create service agent or
          fails to create paired device.
    """
    matching_device = self._FindDeviceInterface(device_address, adapter)
    if not matching_device:
      raise BluetoothManagerException('CreatePairedDevice: '
                                      'Address was not found in scan: %s'
                                      % device_address)
    success = threading.Event()

    def _ReplyHandler():
      """The callback to handle success of device.Pair."""
      logging.info('Paired with device %s.', matching_device)
      success.set()
      self._main_loop.quit()

    def _ErrorHandler(error):
      """The callback to handle error of device.Pair."""
      logging.error('Pairing with device failed: %s.', error)
      if cancel_callback:
        cancel_callback()
      self._main_loop.quit()

    bus = dbus.SystemBus()
    # Exposes a service agent object at a unique path for this test.
    agent_id = str(uuid.uuid4()).replace('-', '')
    agent_path = os.path.join('/BluetoothTest', 'agent', agent_id)
    obj = bus.get_object(BUS_NAME, '/org/bluez')
    agent_manager = dbus.Interface(obj, 'org.bluez.AgentManager1')
    logging.info('CreatePairedDevice: Set agent path at %s.', agent_path)
    try:
      if display_passkey_callback is None:
        capability = 'NoInputNoOutput'
        dbus.service.Object(bus, agent_path)
      else:
        capability = 'KeyboardDisplay'
        AuthenticationAgent(bus, agent_path,
                            display_passkey_callback=display_passkey_callback,
                            cancel_callback=cancel_callback)
      agent_manager.RegisterAgent(agent_path, capability)

    except DBusException as e:
      if str(e).find('there is already a handler.'):
        logging.info('There is already an agent there, that is OK: %s.', e)
      else:
        logging.exception('Fail to create agent.')
        raise BluetoothManagerException('CreatePairedDevice:'
                                        'Fail to create agent.')
    matching_device.Pair(reply_handler=_ReplyHandler,
                         error_handler=_ErrorHandler)
    self._main_loop.run()
    if success.isSet():
      return True
    else:
      raise BluetoothManagerException('Pair: reply_handler'
                                      ' did not get called.')

  def _GetAdapters(self, mac_addr=None):
    """Gets a list of available bluetooth adapters.

    Args:
      mac_addr: The MAC address that adapter should match. None to match any.

    Returns:
      Returns a list of adapters. An adapter is a proxy object which provides
      the interface of 'org.bluez.Adapter1'.

    Raises:
      Raises BluetoothManagerException if fail to get adapter interface.
    """
    objects = self._manager.GetManagedObjects()
    bus = dbus.SystemBus()
    adapters = []
    for path, interfaces in objects.iteritems():
      adapter = interfaces.get(ADAPTER_INTERFACE)
      if adapter is None:
        continue
      if mac_addr and adapter.get(u'Address') != mac_addr:
        continue
      obj = bus.get_object(BUS_NAME, path)
      adapters.append(dbus.Interface(obj, ADAPTER_INTERFACE))
    return adapters

  def GetAdapters(self, max_retry_times=10, interval=2, mac_addr=None):
    """Gets a list of available bluetooth adapters.

    Args:
      max_retry_times: The maximum retry times to find adapters.
      interval: The sleep interval between two trials in seconds.

    Returns:
      A list of adapters found. Each adapter is a proxy object which provides
      the interface of 'org.bluez.Adapter1'. Returns None if there is no
      available adapter.
    """
    adapters = Retry(max_retry_times, interval, None, self._GetAdapters,
                     mac_addr=mac_addr)
    if adapters is None:
      logging.error('BluetoothManager: Fail to get any adapter.')
      return None
    else:
      logging.info('GetAdapters (mac_addr=%s): %s', mac_addr, adapters)
      return adapters

  def _SwitchAdapterPower(self, adapter, on):
    """Powers on adapter by setting the Powered property.

    This will bring up the adapter like 'hciconfig <DEV> up' does.

    Args:
      adapter: The adapter proxy object.
      on: True/False for power on/off.
    """
    bus = dbus.SystemBus()
    device_prop = dbus.Interface(bus.get_object(BUS_NAME, adapter.object_path),
                                 'org.freedesktop.DBus.Properties')
    device_prop.Set(ADAPTER_INTERFACE, 'Powered', on)

  def _WaitUntilStartDiscovery(self, adapter, timeout_secs):
    """Waits until adapter starts discovery mode.

    After calling adapter.StartDiscovery(), there is a delay before the adapter
    actually start scanning. This function blocks until it sees adapter property
    "Discovering" is True with a timeout timeout_secs.
    """
    bus = dbus.SystemBus()
    device_prop = dbus.Interface(bus.get_object(BUS_NAME, adapter.object_path),
                                 'org.freedesktop.DBus.Properties')
    PollForCondition(
        poll_method=lambda: device_prop.Get(ADAPTER_INTERFACE, 'Discovering'),
        condition_method=lambda ret: ret == 1,
        timeout_secs=timeout_secs,
        condition_name='Wait for Discovering==1')

  def RemoveDevices(self, adapter, paths):
    """Lets adapter to remove devices in paths.

    Args:
      adapter: The adapter proxy object.
      paths: A list of device paths to be removed.
    """
    logging.info('Removing devices...')
    for path in paths:
      try:
        adapter.RemoveDevice(path)
      except DBusException as e:
        if str(e).find('Does Not Exist'):
          logging.warning('Can not remove device %s because it is not present',
                          path)

  def GetAllDevicePaths(self, adapter):
    """Gets all device paths under the adapter"""
    introspect = dbus.Interface(adapter, 'org.freedesktop.DBus.Introspectable')
    node_names = _RE_NODE_NAME.findall(introspect.Introspect())
    logging.info('node names: %s', node_names)
    paths = [os.path.join(adapter.object_path, x) for x in node_names]
    logging.info('paths: %s', paths)
    return paths

  def GetAllDevices(self, adapter):
    """Gets all device properties of scanned devices under the adapter

    The returned value is a dict containing the properties of scanned
    devices. Keys are device mac addresses and values are device
    properties.

    Args:
      adapter: The adapter interface to query.

    Returns:
      A dict containing the information of scanned devices. The dict maps
      devices mac addresses to device properties.
    """
    result = {}
    path_prefix = adapter.object_path
    remote_objects = self._manager.GetManagedObjects()
    for path, ifaces in remote_objects.iteritems():
      if path.startswith(path_prefix):
        device = ifaces.get(DEVICE_INTERFACE)
        if device and "Address" in device:
          result[device["Address"]] = device
    return result

  def ScanDevices(self, adapter, timeout_secs=10, match_address=None,
                  remove_before_scan=True):
    """Scans device around using adapter for timeout_secs.

    The returned value devices is a dict containing the properties of
    scanned devies. Keys are device mac addresses and values are device
    properties.
    For example: devices = {
        dbus.String(u'08:3E:8E:2A:90:24'): dbus.Dictionary(
            {dbus.String(u'Paired'): dbus.Boolean(False, variant_level=1),
             dbus.String(u'LegacyPairing'): dbus.Boolean(False,
                                                         variant_level=1),
             dbus.String(u'Alias'): dbus.String(u'08-3E-8E-2A-90-24',
                                                variant_level=1),
             dbus.String(u'Address'): dbus.String(u'08:3E:8E:2A:90:24',
                                                  variant_level=1),
             dbus.String(u'RSSI'): dbus.Int16(-79, variant_level=1),
             dbus.String(u'Class'): dbus.UInt32(0L, variant_level=1),
             dbus.String(u'Trusted'): dbus.Boolean(False, variant_level=1)},
             signature=dbus.Signature('sv'))
        dbus.String(u'00:07:61:FC:0B:E8'): dbus.Dictionary(
            {dbus.String(u'Name'):
                 dbus.String(u'Logitech Bluetooth Mouse M555b',
                             variant_level=1),
             dbus.String(u'Paired'): dbus.Boolean(False, variant_level=1),
             dbus.String(u'LegacyPairing'): dbus.Boolean(False,
                                                         variant_level=1),
             dbus.String(u'Alias'):
                 dbus.String(u'Logitech Bluetooth Mouse M555b',
                             variant_level=1),
             dbus.String(u'Address'): dbus.String(u'00:07:61:FC:0B:E8',
                                                  variant_level=1),
             dbus.String(u'RSSI'): dbus.Int16(-56, variant_level=1),
             dbus.String(u'Class'): dbus.UInt32(9600L, variant_level=1),
             dbus.String(u'Trusted'): dbus.Boolean(False, variant_level=1),
             dbus.String(u'Icon'): dbus.String(u'input-mouse',
                                               variant_level=1)},
             signature=dbus.Signature('sv'))}
    Args:
      adapter: The adapter interface to control.
      timeout_secs: The duration of scan.
      match_address: return the device immediately that matches the MAC address.
                     The purpose is to speed up the scanning.
      remove_before_scan: Remove devices under adapter before scanning.

    Returns:
      A dict containing the information of scanned devices. The dict maps
      devices mac addresses to device properties.
    """

    logging.info('Controlling adapter %s', adapter)
    if remove_before_scan:
      logging.info('Remove old devices before scanning...')
      old_device_paths = self.GetAllDevicePaths(adapter)
      self.RemoveDevices(adapter, old_device_paths)

    # devices is a mapping from device path to device properties.
    devices = dict()
    self._SwitchAdapterPower(adapter, True)
    logging.info('Powered on adapter')

    def _QuitScan(reason):
      """Quit the scan with the given reason.

      Possible reasons
        - timeout occurs
        - the match_address has been found

      Returns:
        False since we want this to be called at most once.
      """
      logging.info(reason)
      adapter.StopDiscovery()
      logging.info('Discovery is stopped.')
      self._main_loop.quit()
      return False

    def _CallbackInterfacesAdded(path, interfaces):
      """The callback when an interface is found.

      When the adapter finds a device, it will assign the device a path and add
      that device interface to dbus.
      Reads the properties of device through interfaces and add the mapping
      from device path to device properties into 'devices'.

      Args:
        path: The device path.
        interfaces: The interface types.
      """
      logging.info('InterfacesAdded')
      if DEVICE_INTERFACE not in interfaces:
        return
      properties = interfaces[DEVICE_INTERFACE]
      for key, value in properties.iteritems():
        logging.debug('%s : %s', key, value)

      if path in devices:
        logging.info('replace old device properties with new device properties')
      devices[path] = properties

      address = (properties['Address'] if 'Address' in properties
                 else '<unknown>')
      logging.info('Bluetooth Device Found: %s.', address)

      if match_address and address == match_address:
        _QuitScan('Device %s found.' % match_address)

      if 'RSSI' in properties:
        logging.info('Address: %s, RSSI: %s', address, properties['RSSI'])

    # pylint: disable=unused-argument
    def _CallbackDevicePropertiesChanged(interface, changed, invalidated, path):
      """The callback when device properties changed.

      This is mainly for debug usage since device is scanned when callback for
      InterfaceAdded is called.

      Args:
        interface: Interface name.
        changed: A dict of changed properties.
        invalidated: A list of properties changed but the value is
          not provided.
        path: The path of signal emitter.
      """
      logging.debug('Device properties changed %s: %s at path %s',
                    interface, changed, path)
      if interface != DEVICE_INTERFACE:
        logging.error('should not get called with interface %s', interface)
        return

      address = (devices[path]['Address']
                 if path in devices and 'Address' in devices[path]
                 else '<unknown>')
      if 'RSSI' in changed:
        logging.info('Address: %s, new RSSI: %s', address, changed['RSSI'])

    bus = dbus.SystemBus()

    bus.add_signal_receiver(_CallbackInterfacesAdded,
                            dbus_interface='org.freedesktop.DBus.ObjectManager',
                            signal_name='InterfacesAdded')

    bus.add_signal_receiver(_CallbackDevicePropertiesChanged,
                            dbus_interface='org.freedesktop.DBus.Properties',
                            signal_name='PropertiesChanged',
                            arg0=DEVICE_INTERFACE,
                            path_keyword='path')

    adapter.StartDiscovery()
    logging.info('Start discovery')
    # Normally it takes less than a second to start discovery.
    # Raises TimeoutError if it fails to start discovery within timeout.
    self._WaitUntilStartDiscovery(adapter, 3)
    logging.info('Device scan started.')

    # Scan for timeout_secs
    gobject.timeout_add(timeout_secs * 1000, _QuitScan, 'Device scan timed out')
    self._main_loop.run()

    bus.remove_signal_receiver(
        _CallbackInterfacesAdded,
        dbus_interface='org.freedesktop.DBus.ObjectManager',
        signal_name='InterfacesAdded')

    bus.remove_signal_receiver(_CallbackDevicePropertiesChanged,
                               dbus_interface='org.freedesktop.DBus.Properties',
                               signal_name='PropertiesChanged',
                               arg0=DEVICE_INTERFACE,
                               path_keyword='path')

    logging.info('Transform the key from path to address...')
    devices_address_properties = dict(
        ((value['Address'], value) for value in devices.values()
         if 'Address' in value))

    return devices_address_properties


USAGE = """
Controls bluetooth adapter to scan remote devices.
"""


class BluetoothTest(object):
  """A class to test bluetooth in command line."""
  args = None
  manager = None
  adapter = None

  def Main(self):
    self.ParseArgs()
    self.Run()

  def ParseArgs(self):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=USAGE)
    parser.add_argument(
        '--properties', dest='properties', action='store_true',
        help='Shows properties in the scanned results')
    parser.add_argument(
        '--forever', dest='forever', action='store_true',
        help='Scans forever')
    self.args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

  def Run(self):
    """Controls the adapter to scan remote devices."""
    self.manager = device_utils.CreateDUTInterface().bluetooth
    self.adapter = self.manager.GetFirstAdapter()
    logging.info('Using adapter: %s', self.adapter)

    if self.args.forever:
      while True:
        self._RunOnce()
    else:
      self._RunOnce()

  def _RunOnce(self):
    """Scans once."""
    result = self.manager.ScanDevices(self.adapter)
    if self.args.properties:
      logging.info(yaml.dump(result, default_flow_style=False))


if __name__ == '__main__':
  BluetoothTest().Main()
