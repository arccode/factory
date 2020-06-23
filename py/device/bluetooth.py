# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from cros.factory.device import device_types


class BluetoothManagerException(Exception):
  pass


class BluetoothManager(device_types.DeviceComponent):
  """The class to handle bluetooth adapter and device.

  Raises:
    Raises BluetoothManagerException
  """

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
    raise NotImplementedError

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
    raise NotImplementedError

  def DisconnectAndUnpairDevice(self, adapter, device_address):
    """Disconnects and unpairs from the device, even if not currently paired.

    This is intended to restore Bluetooth connection status to a known state.

    Args:
      adapter: The adapter interface to control.
      device_address: The mac address of input device to control.

    Returns: Nothing
    """
    raise NotImplementedError

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
    raise NotImplementedError

  def GetFirstAdapter(self, mac_addr=None):
    """Returns the first adapter object found by bluetooth manager.

    An adapter is a proxy object which provides the interface of
    'org.bluez.Adapter1'.

    Args:
      mac_addr: The MAC address that adapter should match. None to match any.

    Raises:
      Raises BluetoothManagerException if fails to get any adapter.
    """
    adapters = self.GetAdapters(mac_addr=mac_addr)
    if adapters:
      return adapters[0]
    raise BluetoothManagerException('Fail to find any adapter.')

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
    raise NotImplementedError

  def RemoveDevices(self, adapter, paths):
    """Lets adapter to remove devices in paths.

    Args:
      adapter: The adapter proxy object.
      paths: A list of device paths to be removed.
    """
    raise NotImplementedError

  def GetAllDevicePaths(self, adapter):
    """Gets all device paths under the adapter"""
    raise NotImplementedError

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
    raise NotImplementedError

  def ScanDevices(self, adapter, timeout_secs=10, match_address=None,
                  remove_before_scan=True):
    """Scans device around using adapter for timeout_secs.

    The returned value devices is a dict containing the properties of
    scanned devies. Keys are device mac addresses and values are device
    properties.

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
    raise NotImplementedError
