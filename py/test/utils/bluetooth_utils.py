# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Bluetooth utils.

Currently, it supports a partial command set of gatttool, i.e., getting the
battery level and the firmware revision string of the target bluetooth device.

This module is mostly inspired by rel_tester.py written by mylesgw@chromium.org
"""

from __future__ import print_function

import argparse
import binascii
import datetime
import logging
import re

from cros.factory.utils import process_utils

from cros.factory.external import pexpect


class BluetoothUtilsError(Exception):
  """An excpetion class for the bluetooth_utils module."""


class BtMgmt:
  """A wrapper of linux btmgmt tool."""

  def __init__(self, manufacturer_id=None):
    self._manufacturer_id = manufacturer_id
    self._hci_device = None
    self._host_mac = None
    self._GetInfo(self._manufacturer_id)

  def _GetInfo(self, manufacturer_id):
    """Get the bluetooth hci device and MAC of the adapter with specified
    manufacturer id.

    If manufacturer_id is None and only one MAC is found, store the one found.
    Raise error when more then one MAC is found and no manufacturer_id is set.

    Examples of the output from "btmgmt info" could be as follows depending
    on the version of btmgmt.

        hci1:   addr 00:1A:7D:DA:71:05 version 6 manufacturer 10 class 0x080104
        ...

    or

        hci0:   Primary controller
                addr 00:1A:7D:DA:71:14 version 6 manufacturer 10 class 0x480104
        ...
    """
    patt = re.compile(
        r'.*\s+addr\s+(.+)\s+version.+manufacturer\s(\d+)\s+class.+')
    hci_device = None
    host_mac_list = []
    for line in process_utils.CheckOutput(['btmgmt', 'info']).splitlines():
      if line.startswith('hci'):
        hci_device = line.split(':')[0]
      # The manufacturer id may or may not be on the same line of
      # the hci device.
      result = patt.match(line)
      if result:
        mid = int(result.group(2))
        if mid == manufacturer_id:
          self._hci_device = hci_device
          self._host_mac = result.group(1)
          return
        host_mac_list.append((hci_device, result.group(1)))
    if len(host_mac_list) > 1:
      raise NotImplementedError('More then one MAC address while no'
                                'mamufacturer_id specified.')
    if len(host_mac_list) == 1:
      self._hci_device = host_mac_list[0][0]
      self._host_mac = host_mac_list[0][1]

  def GetMac(self):
    """Get the MAC address of the bluetooth adapter."""
    return self._host_mac

  def GetHciDevice(self):
    """Get the HCI device of the bluetooth adapter."""
    return self._hci_device

  def FindDevices(self, index=0, timeout_secs=None):
    if self._hci_device:
      index = int(self._hci_device.lstrip('hci'))

    patt = re.compile(
        r'^hci\d+\sdev_found:\s(.+)\stype\s.+\srssi\s(\-\d+)\s.*$')
    devices = {}
    find_cmd = ['btmgmt', '--index', str(index)]
    if timeout_secs is not None:
      find_cmd.extend(['--timeout', str(timeout_secs)])
    find_cmd.append('find')
    for line in process_utils.CheckOutput(find_cmd, log=True).splitlines():
      if line.startswith('hci'):
        result = patt.match(line)
        if not result:
          continue

        mac = result.group(1)
        rssi = int(result.group(2))
        logging.info('Address: %s, RSSI: %d', mac, rssi)
        if mac not in devices:
          devices[mac] = {}
        devices[mac]['RSSI'] = rssi

      elif line.startswith('name'):
        name = line.lstrip('name ')
        devices[mac]['Name'] = name

    # The timeout just kill the interactive session but it may not stop
    # discovery. Use stop-find afterwards to guarantee discovery ends.
    process_utils.CheckOutput(
        ['btmgmt', '--index', str(index), 'stop-find'], log=True)

    return devices


class GattTool:
  """A wrapper of linux gatttool.

  Note: only a limited set of uuids are supported so far, and will be augmented
  on a demand base.
  """

  UUID_BATTERY_LEVEL = '2a19'
  UUID_FIRMWARE_REVISION_STRING = '2a26'

  DEFAULT_LOG_FILE = '/var/log/gatt.log'
  DEFAULT_TIMEOUT = 20

  def __init__(self, target_mac, hci_device=None, logfile=DEFAULT_LOG_FILE,
               timeout=DEFAULT_TIMEOUT):
    # An hci_devices is something like hci0 or hci1.
    hci_option = ''
    if hci_device:
      if hci_device.startswith('hci'):
        hci_option = '-i %s' % hci_device
      else:
        msg = 'hci device "%s" should start with "hci", e.g., hci0 or hci1.'
        logging.warning(msg, hci_device)
    self._gatttool = pexpect.spawn('gatttool %s -b %s -t random --interactive' %
                                   (hci_option, target_mac.upper()))
    self._gatttool.logfile = open(logfile, 'w')
    if timeout is None:
      self._timeout = self.DEFAULT_TIMEOUT
    else:
      self._timeout = timeout

  def __del__(self):
    if not self._gatttool.closed:
      self._gatttool.sendline('exit')
      self._gatttool.logfile.close()
      self._gatttool.close()

  def _RaiseError(self, msg):
    """Raise an error."""
    self.Exit()
    raise BluetoothUtilsError(str(datetime.datetime.now()) + ': ' + msg)

  def ScanAndConnect(self):
    """Scan and connect to the target peer device."""
    try:
      result = self._gatttool.expect(r'\[LE\]>', timeout=self._timeout)
      if result != 0:
        self._RaiseError('scan error')
    except pexpect.TIMEOUT:
      self._RaiseError('scan timeout')

    self._gatttool.sendline('connect')

    try:
      result = self._gatttool.expect('Conn.*', timeout=self._timeout)
      if result != 0:
        self._RaiseError('connection error')
    except pexpect.TIMEOUT:
      self._RaiseError('connection timeout')

  def CharReadUUID(self, uuid, spec_name):
    """Execute char-read-uuid and returns the value.

    Args:
      uuid: an uuid that defines the attribute type
      spec_name: the specification name to display in the log

    Returns:
      the value string
      Note that how to interpret the value string is up to the calling method.

    See details of the complete specification names at
    https://developer.bluetooth.org/gatt/characteristics/Pages/CharacteristicsHome.aspx
    """
    command = 'char-read-uuid %s' % uuid
    self._gatttool.sendline(command)
    # Expect to receive a string like
    #   handle: xxxx   value: ........
    expect_pattern = r'handle:.*\s+value:\s+(.+)\s*\r\n'
    try:
      result = self._gatttool.expect(expect_pattern, timeout=self._timeout)
      if result != 0:
        self._RaiseError('%s error' % command)
      return self._gatttool.match.groups()[0]
    except pexpect.TIMEOUT:
      self._RaiseError('timeout waiting for %s report' % spec_name)

  def _Unhexlify(self, string):
    """Remove spaces and unhexlify the ascii string.

    Args:
      string: the ascii string to unhexlify

    Returns:
      An unhexlified string
    """
    return binascii.unhexlify(string.replace(' ', ''))

  def GetFirmwareRevisionString(self):
    """Get the firmware revision string.

    The version fetched from UUID_FIRMWARE_REVISION_STRING command outputs like

      handle: 0x0010   value: 30 2e 31 35 30 37 31 35

    And the returned value is extracted from the 'value', interpreted as ASCII
    codes. For example, the value above is "0.150715".

    Returns:
      A string representing the firmware revision.
    """
    spec_name = 'firmware revision string'
    result = self.CharReadUUID(self.UUID_FIRMWARE_REVISION_STRING, spec_name)
    return self._Unhexlify(result)

  def GetBatteryLevel(self):
    """Get the battery level.

    An example of the returned battery level, 99, looks like
        handle: 0x0015   value: 63

    Returns:
      An integer representing the battery percentage.
    """
    spec_name = 'battery level'
    result = self.CharReadUUID(self.UUID_BATTERY_LEVEL, spec_name)
    return int(result, 16)

  def Disconnect(self):
    """Send a disconnect command."""
    self._gatttool.sendline('disconnect')

  def Exit(self):
    """Exit and clean up."""
    self.__del__()

  @staticmethod
  def GetDeviceInfo(target_mac, spec_name, hci_device=None, timeout=None):
    """A helper method to get information conveniently from a specified
    bluetooth device.

    Args:
      target_mac: the MAC address of the target device
      spec_name: the specification name to display in the log
      hci_device: the hci device to get information from
    """
    gatttool = GattTool(target_mac, hci_device=hci_device, timeout=timeout)
    gatttool.ScanAndConnect()
    if spec_name == 'battery level':
      info = gatttool.GetBatteryLevel()
    elif spec_name == 'firmware revision string':
      info = gatttool.GetFirmwareRevisionString()
    gatttool.Exit()
    return info


def _ParseCommandLine():
  """Parse the command line options."""
  usage = ('Example:\n\tpython bluetooth_utils.py -a cd:e3:4a:47:1c:e4')
  parser = argparse.ArgumentParser(description=usage)
  parser.add_argument('-a', '--address', action='store', type=str,
                      required=True,
                      help='target address '
                           '(Can be found by running "hcitool lescan")')
  args = parser.parse_args()

  return args


def main():
  """The main program to run the script."""
  args = _ParseCommandLine()
  print('battery level:',
        GattTool.GetDeviceInfo(args.address, 'battery level'))
  print('firmware revision string:',
        GattTool.GetDeviceInfo(args.address, 'firmware revision string'))


if __name__ == '__main__':
  main()
