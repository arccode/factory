#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import service_utils
from cros.factory.utils.service_utils import Status


class ServiceManagerTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.dut = self.mox.CreateMockAnything()

  def tearDown(self):
    self.mox.UnsetStubs()

  def testParseServiceStatus(self):
    self.assertEqual(
        service_utils.ParseServiceStatus('service start/running, process 99'),
        Status.START)
    self.assertEqual(service_utils.ParseServiceStatus('service stop/waiting'),
                     Status.STOP)
    self.assertEqual(
        service_utils.ParseServiceStatus('service: Unknown instance:'),
        Status.UNKNOWN)

  def testGetService(self):
    self.mox.StubOutWithMock(service_utils, 'SetServiceStatus')

    service_utils.SetServiceStatus(
        'started', None, self.dut).AndReturn(Status.START)
    service_utils.SetServiceStatus(
        'raise_exception', None, self.dut).AndRaise(Exception('message'))

    self.mox.ReplayAll()
    self.assertEqual(service_utils.GetServiceStatus('started', dut=self.dut),
                     Status.START)

    with self.assertRaises(Exception):
      service_utils.GetServiceStatus('raise_exception', dut=self.dut)

    self.mox.VerifyAll()

  def testGetServiceIgnoreFailure(self):
    self.mox.StubOutWithMock(service_utils, 'SetServiceStatus')
    service_utils.SetServiceStatus(
        'raise_exception', None, self.dut).AndRaise(Exception('message'))

    self.mox.ReplayAll()

    self.assertEqual(
        service_utils.GetServiceStatus('raise_exception', True, dut=self.dut),
        None)

    self.mox.VerifyAll()

  def testSetServiceStatusWithoutDUT(self):
    self.mox.StubOutWithMock(service_utils, 'CheckOutput')
    self.mox.StubOutWithMock(service_utils, 'ParseServiceStatus')

    commands = {
        None: 'status',
        Status.START: 'start',
        Status.STOP: 'stop'}

    for (status, cmd) in commands.iteritems():
      output = cmd + '_result'
      service_utils.CheckOutput([cmd, 'service']).AndReturn(output)
      service_utils.ParseServiceStatus(output).AndReturn(status)

    self.mox.ReplayAll()

    for status in commands:
      self.assertEqual(service_utils.SetServiceStatus('service', status),
                       status)

    self.mox.VerifyAll()

  def testSetServiceStatusWithDUT(self):
    self.mox.StubOutWithMock(service_utils, 'CheckOutput')
    self.mox.StubOutWithMock(service_utils, 'ParseServiceStatus')

    commands = {
        None: 'status',
        Status.START: 'start',
        Status.STOP: 'stop'}

    for (status, cmd) in commands.iteritems():
      output = cmd + '_result'
      self.dut.CheckOutput([cmd, 'service']).AndReturn(output)
      service_utils.ParseServiceStatus(output).AndReturn(status)

    self.mox.ReplayAll()

    for status in commands:
      self.assertEqual(
          service_utils.SetServiceStatus('service', status, self.dut), status)

    self.mox.VerifyAll()

  def testServiceManager(self):
    self.mox.StubOutWithMock(service_utils, 'GetServiceStatus')
    self.mox.StubOutWithMock(service_utils, 'SetServiceStatus')
    service_utils.GetServiceStatus('stopped_and_enable',
                                   dut=self.dut).AndReturn(Status.STOP)
    service_utils.SetServiceStatus(
        'stopped_and_enable', Status.START, self.dut).AndReturn(Status.START)
    service_utils.GetServiceStatus('started_and_enable',
                                   dut=self.dut).AndReturn(Status.START)
    service_utils.GetServiceStatus('stopped_and_disable',
                                   dut=self.dut).AndReturn(Status.STOP)
    service_utils.GetServiceStatus('started_and_disable',
                                   dut=self.dut).AndReturn(Status.START)
    service_utils.SetServiceStatus(
        'started_and_disable', Status.STOP, self.dut).AndReturn(Status.STOP)
    service_utils.SetServiceStatus(
        'stopped_and_enable', Status.STOP, self.dut).AndReturn(Status.STOP)
    service_utils.SetServiceStatus(
        'started_and_disable', Status.START, self.dut).AndReturn(Status.START)
    self.mox.ReplayAll()

    sm = service_utils.ServiceManager(dut=self.dut)
    sm.SetupServices(
        enable_services=['stopped_and_enable', 'started_and_enable'],
        disable_services=['stopped_and_disable', 'started_and_disable'])
    sm.RestoreServices()

    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
