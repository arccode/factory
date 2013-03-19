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
import threading
import uuid

from cros.factory.test.utils import Retry
from dbus.mainloop.glib import DBusGMainLoop
from dbus import service # pylint: disable=W0611
from dbus import DBusException


class BluetoothManagerException(Exception):
  pass


# TODO(cychiang) Add unittest for this class.
class BluetoothManager(object):
  """The class to handle bluetooth adapter and device through dbus interface.

  Properties:
    _main_loop: The object representing the main event loop of a PyGTK
        application. The main loop should be running when calling function with
        callback through dbus interface.
    _manager: The proxy for the org.bluez.Manager interface on ojbect
        org.bluez/.

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
      self._manager = dbus.Interface(bus.get_object('org.bluez', '/'),
                                    'org.bluez.Manager')
    except DBusException as e:
      raise BluetoothManagerException('DBus Exception in getting Manager'
          'dbus Interface: %s.' % e)

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
    input_interface = dbus.Interface(bus.get_object('org.bluez', device),
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

  def _GetAdapterPaths(self, max_retry_times=10, interval=2):
    """Returns the adapter paths found by bluetooth manager.

    Args:
      max_retry_times: The max retry times to find adapters.
      interval: The sleep interval between each trial in seconds.

    Returns:
      A list of adapters found.
    """
    adapter_paths = Retry(max_retry_times, interval, None,
                          self._manager.ListAdapters)
    if adapter_paths is None:
      logging.error('BluetoothManager: Fail to get any adapter path.')
      return None
    else:
      return adapter_paths

  def GetFirstAdapter(self):
    """Returns the first adapter object found by bluetooth manager.

    An adapter is a proxy object which provides the interface of
    'org.bluez.Adapter'.

    Raises:
      Raises BluetoothManagerException if fail to get any adapter.
    """
    adapter_paths = self._GetAdapterPaths()
    if len(adapter_paths) > 0:
      return self._GetAdapter(adapter_paths[0])
    else:
      raise BluetoothManagerException(
          'GetFirstAdapter: Fail to find any adapter.')

  def _GetAdapter(self, adapter_path):
    """Gets the adapter interface from adapter path.

    Args:
      adapter_path: The path of adapter on dbus.

    Returns:
      Returns the adapter interface, which is a proxy object that provides
      the interface of 'org.bluez.Adapter'.

    Raises:
      Raises BluetoothManagerException if fail to get adapter interface.
    """
    adapter = None
    bus = dbus.SystemBus()
    try:
      adapter = dbus.Interface(bus.get_object('org.bluez', adapter_path),
                               'org.bluez.Adapter')
    except DBusException as e:
      raise BluetoothManagerException('DBus Exception in getting adapter from'
          'path %s: %s.' % (adapter_path, e))
    return adapter

  def GetAdapters(self, max_retry_times, interval):
    """Gets a list of available bluetooth adapters.

    Args:
      max_retry_times: The max retry times to find adapters.
      interval: The sleep interval between each trial in seconds.

    Returns:
      A list of adapters found. Each adapter is a proxy object which provides
      the interface of 'org.bluez.Adapter'.
    """
    adapters = []
    adapter_paths = self._GetAdapterPaths(max_retry_times,
                                          interval)
    for adapter_path in adapter_paths:
      adapters.append(self._GetAdapter(adapter_path))
    return adapters


  def ScanDevices(self, adapter, timeout_secs=5, force_quit=False):
    """Scans device around using adapter for timeout_secs.

    The returned value devices is a dict containing the properties of
    scanned devies.  Keys are device mac addresses and values are device
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
      force_quit: Returns without waiting for Discovery=1.

    Returns:
      A dict containing the information of scanned devices. The dict maps
      devices mac addresses to device properties.
    """

    devices = dict()
    scan_finished = threading.Event()

    def _ScanTimeout():
      """The callback when scan duration is over.

      If adapter is still scanning, stop it and
      quit self._main_loop.

      Returns:
        False since we want this to be called at most once.
      """
      logging.info('Device scan timed out.')
      if not scan_finished.isSet():
        adapter.StopDiscovery()
        if force_quit:
          logging.info('Returns without waiting for Discovery=1.')
          self._main_loop.quit()
      else:
        logging.info('Device scan had already finished.')
      return False

    def _CallbackPropertyChanged(name, value):
      """The callback when adapter property changes.

      Quit self._main_loop if property "Discovering" == 0.

      Args:
        name: The name of property.
        value: The value of that property.
      """
      logging.info('Property Changed: %s = %s.', name, value)
      if (name == 'Discovering' and value == 0):
        logging.info('Finished device scan.')
        scan_finished.set()
        self._main_loop.quit()

    def _CallbackDeviceFound(address, properties): # pylint: disable=W0613
      """The callback when a device is found.

      Add the mapping from device address to properties into
      devices.

      Args:
        address: The device mac address.
        properties: A dict containing device properties.
      """
      logging.info('Bluetooth Device Found: %s.', address)
      for key, value in properties.iteritems():
        logging.info(str(key) + ' : ' + str(value))
      devices[address] = properties

    bus = dbus.SystemBus()
    bus.add_signal_receiver(_CallbackDeviceFound,
                            dbus_interface = 'org.bluez.Adapter',
                            signal_name = 'DeviceFound')
    bus.add_signal_receiver(_CallbackPropertyChanged,
                            dbus_interface = 'org.bluez.Adapter',
                            signal_name = 'PropertyChanged')
    logging.info('Starting device scan.')
    adapter.SetProperty('Powered', True)
    adapter.StartDiscovery()

    # Scan for timeout_secs
    gobject.timeout_add(timeout_secs * 1000, _ScanTimeout)
    self._main_loop.run()

    bus.remove_signal_receiver(_CallbackDeviceFound,
                               dbus_interface = 'org.bluez.Adapter',
                               signal_name = 'DeviceFound')
    bus.remove_signal_receiver(_CallbackPropertyChanged,
                               dbus_interface = 'org.bluez.Adapter',
                               signal_name = 'PropertyChanged')
    logging.info('Scanned Devices: %s', devices)
    return devices

