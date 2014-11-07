#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.system import service_manager
from cros.factory.system.service_manager import Status


class ServiceManagerTest(unittest.TestCase):
  def runTest(self):
    self.assertEqual(
        service_manager.ParseServiceStatus('service start/running, process 99'),
        Status.START)
    self.assertEqual(service_manager.ParseServiceStatus('service stop/waiting'),
                     Status.STOP)
    self.assertEqual(
        service_manager.ParseServiceStatus('service: Unknown instance:'),
        Status.UNKNOWN)

    m = mox.Mox()
    m.StubOutWithMock(service_manager, 'GetServiceStatus')
    m.StubOutWithMock(service_manager, 'SetServiceStatus')
    service_manager.GetServiceStatus('stopped_and_enable').AndReturn(
        Status.STOP)
    service_manager.SetServiceStatus('stopped_and_enable',
                                     Status.START).AndReturn(Status.START)
    service_manager.GetServiceStatus('started_and_enable').AndReturn(
        Status.START)
    service_manager.GetServiceStatus('stopped_and_disable').AndReturn(
        Status.STOP)
    service_manager.GetServiceStatus('started_and_disable').AndReturn(
        Status.START)
    service_manager.SetServiceStatus('started_and_disable',
                                     Status.STOP).AndReturn(Status.STOP)
    service_manager.SetServiceStatus('stopped_and_enable',
                                     Status.STOP).AndReturn(Status.STOP)
    service_manager.SetServiceStatus('started_and_disable',
                                     Status.START).AndReturn(Status.START)
    m.ReplayAll()

    sm = service_manager.ServiceManager()
    sm.SetupServices(
        enable_services=['stopped_and_enable', 'started_and_enable'],
        disable_services=['stopped_and_disable', 'started_and_disable'])
    sm.RestoreServices()

    m.UnsetStubs()
    m.VerifyAll()


if __name__ == '__main__':
  unittest.main()
