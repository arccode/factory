#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for servo_client."""

import unittest
from unittest import mock

from cros.factory.test.fixture.whale import servo_client


class ServoClientTest(unittest.TestCase):

  def setUp(self):
    self.server_mock = mock.MagicMock()
    self.client = servo_client.ServoClient(host='127.0.0.1', port='9999')
    self.client.__setattr__('_server', self.server_mock)

  def testGet(self):
    self.server_mock.get.return_value = 'on'
    self.assertEqual('on', self.client.Get('dev1'))
    self.server_mock.get.assert_called_with('dev1')

    self.server_mock.get.return_value = '1'
    self.assertEqual('1', self.client.Get('dev2'))
    self.server_mock.get.assert_called_with('dev2')

    self.server_mock.get.side_effect = Exception('no such dev')
    self.assertRaises(servo_client.ServoClientError, self.client.Get,
                      'dev_unknown')
    self.server_mock.get.assert_called_with('dev_unknown')

  def testMultipleGet(self):
    self.server_mock.set_get_all.return_value = ['on', 'off']
    self.assertDictEqual({'dev1': 'on', 'dev2': 'off'},
                         self.client.MultipleGet(['dev1', 'dev2']))
    self.server_mock.set_get_all.assert_called_with(['dev1', 'dev2'])

    self.server_mock.set_get_all.side_effect = Exception('no such dev')
    self.assertRaises(servo_client.ServoClientError,
                      self.client.MultipleGet, ['dev1', 'dev_unknown'])
    self.server_mock.set_get_all.assert_called_with(['dev1', 'dev_unknown'])

  def testIsOn(self):
    self.server_mock.get.return_value = 'on'
    self.assertEqual(True, self.client.IsOn('dev1'))
    self.server_mock.get.assert_called_with('dev1')

    self.server_mock.get.return_value = 'off'
    self.assertEqual(False, self.client.IsOn('dev2'))
    self.server_mock.get.assert_called_with('dev2')

    self.server_mock.get.return_value = '1'
    self.assertRaises(servo_client.ServoClientError, self.client.IsOn, 'dev3')
    self.server_mock.get.assert_called_with('dev3')

  def testMultipleIsOn(self):
    self.server_mock.set_get_all.return_value = ['on', 'off']
    self.assertDictEqual({'dev1': True, 'dev2': False},
                         self.client.MultipleIsOn(['dev1', 'dev2']))
    self.server_mock.set_get_all.assert_called_with(['dev1', 'dev2'])

    self.server_mock.set_get_all.side_effect = Exception('no such dev')
    self.assertRaises(servo_client.ServoClientError, self.client.MultipleIsOn,
                      ['dev1', 'dev_unknown'])
    self.server_mock.set_get_all.assert_called_with(['dev1', 'dev_unknown'])

  def testSet(self):
    self.client.Set('dev1', 'on')
    self.server_mock.set.assert_called_with('dev1', 'on')

    self.client.Set('dev2', 'off')
    self.server_mock.set.assert_called_with('dev2', 'off')

    self.server_mock.set.side_effect = Exception()
    self.assertRaises(servo_client.ServoClientError, self.client.Set,
                      'dev_unknown', 'on')
    self.server_mock.set.assert_called_with('dev_unknown', 'on')

  def testMultipleSet(self):
    self.client.MultipleSet([('dev1', 'on'), ('dev2', 'off')])
    self.server_mock.set_get_all.assert_called_with(['dev1:on', 'dev2:off'])

    self.server_mock.set_get_all.side_effect = Exception()
    self.assertRaises(servo_client.ServoClientError, self.client.MultipleSet,
                      [('dev_unknown', 'on'), ('dev2', 'off')])
    self.server_mock.set_get_all.assert_called_with(
        ['dev_unknown:on', 'dev2:off'])

  def testEnable(self):
    self.client.Enable('dev1')
    self.server_mock.set.assert_called_with('dev1', 'on')

    self.server_mock.set.side_effect = Exception()
    self.assertRaises(servo_client.ServoClientError, self.client.Enable,
                      'dev_unknown')
    self.server_mock.set.assert_called_with('dev_unknown', 'on')

  def testDisable(self):
    self.client.Disable('dev1')
    self.server_mock.set.assert_called_with('dev1', 'off')

    self.server_mock.set.side_effect = Exception()
    self.assertRaises(servo_client.ServoClientError, self.client.Disable,
                      'dev_unknown')
    self.server_mock.set.assert_called_with('dev_unknown', 'off')

  def testClick(self):
    self.client.Click('dev1')
    self.server_mock.set_get_all.assert_called_with(['dev1:on', 'dev1:off'])

    self.server_mock.set_get_all.side_effect = Exception()
    self.assertRaises(servo_client.ServoClientError, self.client.Click,
                      'dev_unknown')
    self.server_mock.set_get_all.assert_called_with(
        ['dev_unknown:on', 'dev_unknown:off'])


if __name__ == '__main__':
  unittest.main()
