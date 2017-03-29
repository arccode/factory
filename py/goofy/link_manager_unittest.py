#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import threading
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import link_manager
from cros.factory.goofy.link_manager import DUTLinkManager
from cros.factory.goofy.link_manager import LinkDownError
from cros.factory.goofy.link_manager import PresenterLinkManager
from cros.factory.test import factory
from cros.factory.test.utils import dhcp_utils
from cros.factory.utils import net_utils

_LOCALHOST = '127.0.0.1'
_STANDALONE = 'standalone'

class LinkManagerTest(unittest.TestCase):

  def setUp(self):
    self.dut_link = None
    self.presenter_link = None
    self.dut_connect_event = threading.Event()
    self.dut_disconnect_event = threading.Event()
    self.presenter_connect_event = threading.Event()
    self.presenter_disconnect_event = threading.Event()

    dhcp_server = dhcp_utils.DummyDHCPManager()
    link_manager.dhcp_utils.StartDHCPManager = lambda **kargs: dhcp_server

    link_manager.PRESENTER_LINK_RPC_PORT = net_utils.FindUnusedTCPPort()
    link_manager.PRESENTER_PING_PORT = net_utils.FindUnusedTCPPort()
    link_manager.DUT_LINK_RPC_PORT = net_utils.FindUnusedTCPPort()
    link_manager.DUT_PING_PORT = net_utils.FindUnusedTCPPort()

    net_utils.StartNATService = lambda x, y: None

  def tearDown(self):
    if self.dut_link:
      self.dut_link.Stop()
    if self.presenter_link:
      self.presenter_link.Stop()

  def Echo(self, s):
    return s

  def ClearEvents(self):
    for e in [self.dut_connect_event, self.dut_disconnect_event,
              self.presenter_connect_event, self.presenter_disconnect_event]:
      e.clear()

  def StartPresenter(self):
    self.dut_link = DUTLinkManager(
        check_interval=0.1,
        methods={'Echo1': self.Echo},
        connect_hook=lambda *unused_args: self.dut_connect_event.set(),
        disconnect_hook=lambda *unused_args: self.dut_disconnect_event.set())
    self.dut_link.Start()

  def StopPresenter(self):
    self.dut_link.Stop()
    self.dut_link = None

  def StartDUT(self):
    self.presenter_link = PresenterLinkManager(
        check_interval=0.1, methods={
            'Echo': self.Echo
        },
        connect_hook=lambda *unused_args: self.presenter_connect_event.set(),
        disconnect_hook=lambda *unused_args: (
            self.presenter_disconnect_event.set()))
    if self.dut_link:
      self.dut_link.OnDHCPEvent(_LOCALHOST, _STANDALONE)

  def StopDUT(self):
    self.presenter_link.Stop()
    self.presenter_link = None

  def testLink(self):
    self.StartPresenter()
    self.StartDUT()

    self.assertTrue(self.presenter_connect_event.wait(0.5))
    self.assertTrue(self.dut_connect_event.isSet())
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsConnected())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.presenter_link.Echo1(10), 10)

    self.StopDUT()

    self.assertTrue(self.dut_disconnect_event.wait(0.5))
    self.assertFalse(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertRaises(LinkDownError, lambda: self.dut_link.Echo('test'))

    self.ClearEvents()
    self.StartDUT()

    self.assertTrue(self.presenter_connect_event.wait(0.5))
    self.assertTrue(self.dut_connect_event.isSet())
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsConnected())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.presenter_link.Echo1(10), 10)

    # Should not call disconnect hook if monitoring is stopped
    self.ClearEvents()
    self.presenter_link.SuspendMonitoring(1)
    self.StopDUT()
    self.assertFalse(self.presenter_disconnect_event.wait(0.5))

    self.StartDUT()
    self.assertTrue(self.presenter_connect_event.wait(0.5))
    self.assertTrue(self.dut_connect_event.isSet())

    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsConnected())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.presenter_link.Echo1(10), 10)
    self.presenter_link.ResumeMonitoring()

    # A glitch in DUT ping response
    self.ClearEvents()
    self.presenter_link.StopPingServer()
    self.assertTrue(self.dut_disconnect_event.wait(0.5))
    self.assertTrue(self.presenter_disconnect_event.wait(0.5))

    self.presenter_link.StartPingServer()
    self.assertTrue(self.dut_connect_event.wait(0.5))
    self.assertTrue(self.presenter_connect_event.wait(0.5))
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsConnected())

if __name__ == '__main__':
  factory.init_logging()
  unittest.main()
