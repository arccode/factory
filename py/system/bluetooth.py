#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import dbus
import factory_common # pylint: disable=W0611
import gobject
import logging
import os
import re
import threading
import uuid

from cros.factory.test.utils import Retry
from cros.factory.utils.net_utils import PollForCondition
from dbus.mainloop.glib import DBusGMainLoop
from dbus import service # pylint: disable=W0611
from dbus import DBusException


BUS_NAME = 'org.bluez'
SERVICE_NAME = 'org.bluez'
ADAPTER_INTERFACE = SERVICE_NAME + '.Adapter1'
DEVICE_INTERFACE = SERVICE_NAME + '.Device1'

_RE_NODE_NAME = re.compile(r'<node name="(.*?)"/>')


class BluetoothManagerException(Exception):
  pass


#TODO(cychiang) Add unittest for this class.
class BluetoothManager(object):
  """The class to handle bluetooth adapter and device through dbus interface.

  Properties:
    _main_loop: The object representing the main event loop of a PyGTK
        application. The main loop should be running when calling function with
        callback through dbus interface.
    _manager: The proxy for the org.freedesktoop.DBus.ObjectManager interface
        on ojbect path / on bus org.bluez.

  Raises:
    Raises BluetoothManagerException if org.bluez.Manager object is not
    available through dbus interface.
  """
  def __init__(self):
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

  #TODO(cychiang). Migrate to bluez5.x api. Check crosbug.com/p/19276.
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
      device = adapter.FindDevice(device_address)
    except DBusException as e:
      raise BluetoothManagerException('SetDeviceConnected: fail to find device'
                                      ' %s: %s' % (device_address, e))
    bus = dbus.SystemBus()
    input_interface = dbus.Interface(bus.get_object(BUS_NAME, device),
                                     'org.bluez.Input')
    try:
      if connect:
        input_interface.Connect()
      else:
        input_interface.Disconnect()
    except DBusException as e:
      raise BluetoothManagerException('SetDeviceConnected: fail to switch'
                                      'connection: %s' % e)
    else:
      return True

  #TODO(cychiang). Migrate to bluez5.x api. Check crosbug.com/p/19276.
  def RemovePairedDevice(self, adapter, device_address):
    """Removes the paired device.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.

    Returns:
      Return True if succeed to remove paired device.

    Raises:
      Raises BluetoothManagerException if fail to remove paired device.
    """
    try:
      device = adapter.FindDevice(device_address)
      adapter.RemoveDevice(device)
    except DBusException as e:
      raise BluetoothManagerException('RemovePairedDevice: fail to remove'
                                      ' device: %s.' % e)
    else:
      logging.info('succefully removed device.')
      return True

  #TODO(cychiang). Migrate to bluez5.x api. Check crosbug.com/p/19276.
  def CreatePairedDevice(self, adapter, device_address):
    """Create paired device.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.

    Raises:
      Raises BluetoothManagerException if fails to create service agent or
          fails to create paired device.
    """
    success = threading.Event()

    def _ReplyHandler(device):
      """The callback to handle success of adapter.CreatePairedDevice."""
      logging.info('Created device %s.', device)
      success.set()
      self._main_loop.quit()

    def _ErrorHandler(error):
      """The callback to handle error of adapter.CreatePairedDevice."""
      logging.error('Creating device failed: %s.', error)
      self._main_loop.quit()

    bus = dbus.SystemBus()
    # Exposes a service agent object at a unique path for this test.
    agent_id = str(uuid.uuid4()).replace('-', '')
    agent_path = os.path.join('/BluetoothTest', 'agent', agent_id)
    logging.info('CreatePairedDevice: Set agent path at %s.', agent_path)

    try:
      dbus.service.Object(bus, agent_path)
    except DBusException as e:
      if str(e).find('there is already a handler.'):
        logging.info('There is already an agent there, that is OK: %s.', e)
      else:
        logging.exception('Fail to create agent.')
        raise BluetoothManagerException('CreatePairedDevice:'
                                        'Fail to create agent.')
    adapter.CreatePairedDevice(device_address, agent_path, 'DisplayYesNo',
                               reply_handler=_ReplyHandler,
                               error_handler=_ErrorHandler)
    self._main_loop.run()
    if success.isSet():
      return True
    else:
      raise BluetoothManagerException('CreatePairedDevice: reply_handler'
          ' did not get called.')

  def GetFirstAdapter(self):
    """Returns the first adapter object found by bluetooth manager.

    An adapter is a proxy object which provides the interface of
    'org.bluez.Adapter1'.

    Raises:
      Raises BluetoothManagerException if fails to get any adapter.
    """
    adapters = self.GetAdapters()
    if len(adapters) > 0:
      return adapters[0]
    else:
      raise BluetoothManagerException('Fail to find any adapter.')

  def _GetAdapters(self):
    """Gets a list of available bluetooth adapters.

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
      obj = bus.get_object(BUS_NAME, path)
      adapters.append(dbus.Interface(obj, ADAPTER_INTERFACE))
    return adapters

  def GetAdapters(self, max_retry_times=10, interval=2):
    """Gets a list of available bluetooth adapters.

    Args:
      max_retry_times: The maximum retry times to find adapters.
      interval: The sleep interval between two trials in seconds.

    Returns:
      A list of adapters found. Each adapter is a proxy object which provides
      the interface of 'org.bluez.Adapter1'. Returns None if there is no
      available adapter.
    """
    adapters = Retry(max_retry_times, interval, None,
                     self._GetAdapters)
    if adapters is None:
      logging.error('BluetoothManager: Fail to get any adapter.')
      return None
    else:
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
    _Condition = lambda: device_prop.Get(ADAPTER_INTERFACE, 'Discovering') == 1
    PollForCondition(_Condition, timeout_secs,
                     condition_name="Wait for Discovering==1")

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

  def ScanDevices(self, adapter, timeout_secs=10, remove_before_scan=True):
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

    def _ScanTimeout():
      """The callback when scan duration is over.

      If adapter is still scanning, stop it and
      quit self._main_loop.

      Returns:
        False since we want this to be called at most once.
      """
      logging.info('Device scan timed out.')
      adapter.StopDiscovery()
      logging.info('Stop Discovery')
      logging.info('Quit main loop without waiting for Discovery=1.')
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
        logging.debug(str(key) + ' : ' + str(value))

      if path in devices:
        logging.info('replace old device properties with new device properties')
      devices[path] = properties

      address = (properties['Address'] if 'Address' in properties
                 else '<unknown>')
      logging.info('Bluetooth Device Found: %s.', address)
      if 'RSSI' in properties:
        logging.info('Address: %s, RSSI: %s', address, properties['RSSI'])

    # pylint: disable=W0613
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
        path_keyword="path")

    adapter.StartDiscovery()
    logging.info('Start discovery')
    # Normally it takes less than a second to start discovery.
    # Raises TimeoutError if it fails to start discovery within timeout.
    self._WaitUntilStartDiscovery(adapter, 3)
    logging.info('Device scan started.')

    # Scan for timeout_secs
    gobject.timeout_add(timeout_secs * 1000, _ScanTimeout)
    self._main_loop.run()

    bus.remove_signal_receiver(_CallbackInterfacesAdded,
        dbus_interface='org.freedesktop.DBus.ObjectManager',
        signal_name='InterfacesAdded')

    bus.remove_signal_receiver(_CallbackDevicePropertiesChanged,
        dbus_interface='org.freedesktop.DBus.Properties',
        signal_name='PropertiesChanged',
        arg0=DEVICE_INTERFACE,
        path_keyword="path")

    logging.info('Transform the key from path to address...')
    devices_address_properties = dict(
        ((value['Address'], value) for value in devices.values()
         if 'Address' in value))

    return devices_address_properties
