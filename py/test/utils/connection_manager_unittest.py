#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from unittest import mock

import dbus

from cros.factory.test.utils import connection_manager
from cros.factory.utils.net_utils import WLAN


_FAKE_MANAGER = 'flimflam'
_FAKE_PROC_NAME = 'shill'
_FAKE_SCAN_INTERVAL_SECS = 10
_FAKE_DEPSERVICE_LIST = ['wpasupplicant']
_FAKE_SUBSERVICE_LIST = ['flimflam_respawn', 'modemmanager']
_FAKE_PROFILE_LOCATION = '/var/cache/%s/default.profile'
_FAKE_INTERFACES = ['wlan0', 'eth0', 'lo']
_FAKE_OVERRIDE_BLOCKED_DEVICES = ['wlan0']
_FAKE_DATA = {
    'scan_interval': _FAKE_SCAN_INTERVAL_SECS,
    'network_manager': _FAKE_MANAGER,
    'process_name': _FAKE_PROC_NAME,
    'depservices': _FAKE_DEPSERVICE_LIST,
    'subservices': _FAKE_SUBSERVICE_LIST,
    'profile_path': _FAKE_PROFILE_LOCATION,
    'override_blocklisted_devices': None,
}


class WLANTest(unittest.TestCase):

  def testWLANFailWPASecurity(self):
    self.assertRaises(ValueError, WLAN,
                      ssid='fake_server1', security='wpa', passphrase='1')

  def testWLANFailInvalidSecurity(self):
    self.assertRaises(ValueError, WLAN,
                      ssid='fake_server1', security='ABC', passphrase='1')


class ConnectionManagerTest(unittest.TestCase):

  def setUp(self):
    self.fakeBaseNetworkManager = mock.MagicMock()
    self.fakeData = _FAKE_DATA.copy()
    self.fakeData['wlans'] = [WLAN(ssid='fake_server',
                                   security='psk',
                                   passphrase='test0000')]

  def GetDisableNetworkingSubprocessCalls(self):
    subprocess_call_calls = []
    for service in (_FAKE_SUBSERVICE_LIST + [_FAKE_MANAGER] +
                    _FAKE_DEPSERVICE_LIST):
      subprocess_call_calls.append(
          mock.call('stop %s' % service, shell=True, stdout=mock.ANY,
                    stderr=mock.ANY))

    interfaces = list(_FAKE_INTERFACES)
    interfaces.remove('lo')
    for dev in interfaces:
      subprocess_call_calls.append(
          mock.call('ifconfig %s down' % dev, shell=True, stdout=mock.ANY,
                    stderr=mock.ANY))

    return subprocess_call_calls

  def VerifyDisableNetworking(self, glob_mock, call_mock):
    glob_mock.assert_called_once_with('/sys/class/net/*')
    self.assertEqual(call_mock.call_args_list,
                     self.GetDisableNetworkingSubprocessCalls())

  def MockEnableNetworking(self):
    fakeDevice = mock.MagicMock()
    fakeDevice.ScanInterval = dbus.UInt16(_FAKE_SCAN_INTERVAL_SECS)
    self.fakeBaseNetworkManager.FindElementByNameSubstring = mock.Mock(
        return_value=fakeDevice)

    self.fakeBaseNetworkManager.manager = mock.MagicMock()

  def GetEnableNetworkingSubprocessCalls(self):
    subprocess_call_calls = []
    interfaces = list(_FAKE_INTERFACES)
    interfaces.remove('lo')

    for dev in interfaces:
      subprocess_call_calls.append(
          mock.call('ifconfig %s up' % dev, shell=True, stdout=mock.ANY,
                    stderr=mock.ANY))

    for service in (_FAKE_DEPSERVICE_LIST + [_FAKE_MANAGER] +
                    _FAKE_SUBSERVICE_LIST):
      cmd = 'start %s' % service
      if (service in [_FAKE_MANAGER] and
          self.fakeData['override_blocklisted_devices'] is not None):
        cmd += ' BLOCKED_DEVICES="%s"' % (
            ','.join(self.fakeData['override_blocklisted_devices']))
      subprocess_call_calls.append(
          mock.call(cmd, shell=True, stdout=mock.ANY, stderr=mock.ANY))

    return subprocess_call_calls

  def VerifyEnableNetworking(self, glob_mock, call_mock, remove_mock=None,
                             reset=True):
    subprocess_call_calls = []
    glob_call_count = 2

    if reset:
      remove_mock.assert_called_once_with(_FAKE_PROFILE_LOCATION %
                                          _FAKE_PROC_NAME)
      subprocess_call_calls.extend(self.GetDisableNetworkingSubprocessCalls())
      glob_call_count += 1
    subprocess_call_calls.extend(self.GetEnableNetworkingSubprocessCalls())

    self.assertEqual(call_mock.call_args_list, subprocess_call_calls)
    self.fakeBaseNetworkManager.FindElementByNameSubstring.assert_called_with(
        'Device', 'wlan0')
    self.fakeBaseNetworkManager.manager.ConfigureService.assert_called_with({
        'Type': 'wifi',
        'Mode': 'managed',
        'AutoConnect': True,
        'SSID': 'fake_server',
        'SecurityClass': 'psk',
        'Passphrase': 'test0000'
    }, signature=mock.ANY)
    connection_manager.GetBaseNetworkManager.assert_called_once_with()
    glob_mock.assert_called_with('/sys/class/net/*')
    self.assertEqual(glob_call_count, glob_mock.call_count)

  @mock.patch(connection_manager.__name__ + '.GetBaseNetworkManager')
  @mock.patch('subprocess.call')
  @mock.patch('glob.glob')
  def testInitWithEnableNetworking(self, glob_mock, call_mock,
                                   get_base_network_manager_mock):
    glob_mock.return_value = _FAKE_INTERFACES
    get_base_network_manager_mock.return_value = self.fakeBaseNetworkManager

    self.MockEnableNetworking()

    connection_manager.ConnectionManager(start_enabled=True,
                                         **self.fakeData)
    self.VerifyEnableNetworking(glob_mock, call_mock, reset=False)

  @mock.patch('subprocess.call')
  @mock.patch('glob.glob')
  def testInitWithDisableNetworking(self, glob_mock, call_mock):
    glob_mock.return_value = _FAKE_INTERFACES

    connection_manager.ConnectionManager(start_enabled=False,
                                         **self.fakeData)
    self.VerifyDisableNetworking(glob_mock, call_mock)

  @mock.patch(connection_manager.__name__ + '.GetBaseNetworkManager')
  @mock.patch('os.remove')
  @mock.patch('subprocess.call')
  @mock.patch('glob.glob')
  def testOverrideBlocklistedDevices(self, glob_mock, call_mock, remove_mock,
                                     get_base_network_manager_mock):
    glob_mock.return_value = _FAKE_INTERFACES
    get_base_network_manager_mock.return_value = self.fakeBaseNetworkManager
    self.fakeData['override_blocklisted_devices'] = (
        _FAKE_OVERRIDE_BLOCKED_DEVICES)
    self.MockEnableNetworking()

    connection_manager.ConnectionManager(start_enabled=True,
                                         **self.fakeData)
    self.VerifyEnableNetworking(glob_mock, call_mock, remove_mock, reset=True)

  def testInitFailInvalidNetworkManager(self):
    self.assertRaises(AssertionError, connection_manager.ConnectionManager,
                      network_manager='ABC')

  def testInitFailInvalidProcessName(self):
    self.assertRaises(AssertionError, connection_manager.ConnectionManager,
                      process_name='XYZ')

  @mock.patch(connection_manager.__name__ + '.GetBaseNetworkManager')
  @mock.patch('subprocess.call')
  @mock.patch('glob.glob')
  def testIsConnectedOK(self, glob_mock, call_mock,
                        get_base_network_manager_mock):
    glob_mock.return_value = _FAKE_INTERFACES
    get_base_network_manager_mock.return_value = self.fakeBaseNetworkManager
    self.fakeBaseNetworkManager.GetSystemState.return_value = 'online'

    x = connection_manager.ConnectionManager(start_enabled=False,
                                             **self.fakeData)
    self.assertEqual(x.IsConnected(), True)
    self.VerifyDisableNetworking(glob_mock, call_mock)

  @mock.patch(connection_manager.__name__ + '.GetBaseNetworkManager')
  @mock.patch('subprocess.call')
  @mock.patch('glob.glob')
  def testIsConnectedFailNotConnected(self, glob_mock, call_mock,
                                      get_base_network_manager_mock):
    glob_mock.return_value = _FAKE_INTERFACES
    get_base_network_manager_mock.return_value = self.fakeBaseNetworkManager
    self.fakeBaseNetworkManager.GetSystemState.return_value = 'offline'

    x = connection_manager.ConnectionManager(start_enabled=False,
                                             **self.fakeData)
    self.assertEqual(x.IsConnected(), False)
    self.VerifyDisableNetworking(glob_mock, call_mock)

  @mock.patch(connection_manager.__name__ + '.GetBaseNetworkManager')
  @mock.patch('subprocess.call')
  @mock.patch('glob.glob')
  def testIsConnectedFailNetworkManagerNotRunning(
      self, glob_mock, call_mock, get_base_network_manager_mock):
    glob_mock.return_value = _FAKE_INTERFACES
    get_base_network_manager_mock.side_effect = dbus.exceptions.DBusException(
        'YAYA')

    x = connection_manager.ConnectionManager(start_enabled=False,
                                             **self.fakeData)
    self.assertEqual(x.IsConnected(), False)
    self.VerifyDisableNetworking(glob_mock, call_mock)


if __name__ == '__main__':
  unittest.main()
