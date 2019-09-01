#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy
from cros.factory.goofy.plugins import device_manager


class DeviceManagerTest(unittest.TestCase):

  def setUp(self):
    self.dm = device_manager.DeviceManager(mock.Mock(goofy.Goofy))

  @mock.patch('cros.factory.goofy.plugins.device_manager.sys_utils')
  def testGetVarLogMessages(self, sys_utils):
    var_log_messages = 'foo\xFF\nbar\n'
    expected_output = u'foo\ufffd\nbar\n'
    sys_utils.GetVarLogMessages.return_value = var_log_messages
    data = self.dm.GetVarLogMessages()
    self.assertEqual(expected_output, data.data)

  @mock.patch('cros.factory.goofy.plugins.device_manager.sys_utils')
  def testGetVarLogMessagesBeforeReboot(self, sys_utils):
    var_log_messages = 'foo\xFF\nbar\n'
    expected_output = u'foo\ufffd\nbar\n'
    sys_utils.GetVarLogMessagesBeforeReboot.return_value = var_log_messages
    data = self.dm.GetVarLogMessagesBeforeReboot()
    self.assertEquals(expected_output, data.data)

  @mock.patch.multiple('cros.factory.goofy.plugins.device_manager',
                       process_utils=mock.DEFAULT,
                       time=mock.DEFAULT)
  def testGetDmesg(self, process_utils, time):
    # pylint: disable=protected-access
    device_manager.DeviceManager._ReadUptime = mock.Mock()

    process_utils.Spawn.return_value = type(
        '', (object,), dict(stdout_data='[ 123.0] A\n[2345.0] B\n'))
    device_manager.DeviceManager._ReadUptime.return_value = '3000.0'
    time.time.return_value = 1343806777.0

    self.assertEquals('2012-08-01T06:51:40.000Z [ 123.0] A\n'
                      '2012-08-01T07:28:42.000Z [2345.0] B\n',
                      self.dm.GetDmesg().data)
    process_utils.Spawn.assert_called_once_with(
        ['dmesg'], check_call=True, read_stdout=True)


if __name__ == '__main__':
  unittest.main()
