#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for servo_client."""

import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.test.fixture.whale import servo_client


class ServoClientTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.server_mock = self.mox.CreateMockAnything()
    self.client = servo_client.ServoClient(host='127.0.0.1', port='9999')
    self.client.__setattr__('_server', self.server_mock)

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()

  def testGet(self):
    self.server_mock.get('dev1').AndReturn('on')
    self.server_mock.get('dev2').AndReturn('1')
    self.server_mock.get('dev_unknown').AndRaise(Exception('no such dev'))
    self.mox.ReplayAll()

    self.assertEqual('on', self.client.Get('dev1'))
    self.assertEqual('1', self.client.Get('dev2'))
    self.assertRaises(servo_client.ServoClientError, self.client.Get,
                      'dev_unknown')

  def testMultipleGet(self):
    self.server_mock.set_get_all(['dev1', 'dev2']).AndReturn(['on', 'off'])
    self.server_mock.set_get_all(['dev1', 'dev_unknown']).AndRaise(
        Exception('no such dev'))
    self.mox.ReplayAll()

    self.assertDictEqual({'dev1': 'on', 'dev2': 'off'},
                         self.client.MultipleGet(['dev1', 'dev2']))
    self.assertRaises(servo_client.ServoClientError,
                      self.client.MultipleGet, ['dev1', 'dev_unknown'])

  def testIsOn(self):
    self.server_mock.get('dev1').AndReturn('on')
    self.server_mock.get('dev2').AndReturn('off')
    self.server_mock.get('dev3').AndReturn('1')
    self.mox.ReplayAll()

    self.assertEqual(True, self.client.IsOn('dev1'))
    self.assertEqual(False, self.client.IsOn('dev2'))
    self.assertRaises(servo_client.ServoClientError, self.client.IsOn, 'dev3')

  def testMultipleIsOn(self):
    self.server_mock.set_get_all(['dev1', 'dev2']).AndReturn(['on', 'off'])
    self.server_mock.set_get_all(['dev1', 'dev_unknown']).AndRaise(
        Exception('no such dev'))
    self.mox.ReplayAll()

    self.assertDictEqual({'dev1': True, 'dev2': False},
                         self.client.MultipleIsOn(['dev1', 'dev2']))
    self.assertRaises(servo_client.ServoClientError, self.client.MultipleIsOn,
                      ['dev1', 'dev_unknown'])

  def testSet(self):
    self.server_mock.set('dev1', 'on')
    self.server_mock.set('dev2', 'off')
    self.server_mock.set('dev_unknown', 'on').AndRaise(Exception())
    self.mox.ReplayAll()

    self.client.Set('dev1', 'on')
    self.client.Set('dev2', 'off')
    self.assertRaises(servo_client.ServoClientError, self.client.Set,
                      'dev_unknown', 'on')

  def testMultipleSet(self):
    self.server_mock.set_get_all(['dev1:on', 'dev2:off'])
    self.server_mock.set_get_all(['dev_unknown:on', 'dev2:off']).AndRaise(
        Exception())
    self.mox.ReplayAll()

    self.client.MultipleSet([('dev1', 'on'), ('dev2', 'off')])
    self.assertRaises(servo_client.ServoClientError, self.client.MultipleSet,
                      [('dev_unknown', 'on'), ('dev2', 'off')])

  def testEnable(self):
    self.server_mock.set('dev1', 'on')
    self.server_mock.set('dev_unknown', 'on').AndRaise(Exception())
    self.mox.ReplayAll()

    self.client.Enable('dev1')
    self.assertRaises(servo_client.ServoClientError, self.client.Enable,
                      'dev_unknown')

  def testDisable(self):
    self.server_mock.set('dev1', 'off')
    self.server_mock.set('dev_unknown', 'off').AndRaise(Exception())
    self.mox.ReplayAll()

    self.client.Disable('dev1')
    self.assertRaises(servo_client.ServoClientError, self.client.Disable,
                      'dev_unknown')

  def testClick(self):
    self.server_mock.set_get_all(['dev1:on', 'dev1:off'])
    self.server_mock.set_get_all(
        ['dev_unknown:on', 'dev_unknown:off']).AndRaise(Exception())
    self.mox.ReplayAll()

    self.client.Click('dev1')
    self.assertRaises(servo_client.ServoClientError, self.client.Click,
                      'dev_unknown')


if __name__ == '__main__':
  unittest.main()
