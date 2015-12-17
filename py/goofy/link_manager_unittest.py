#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import link_manager
from cros.factory.goofy.link_manager import DUTLinkManager
from cros.factory.goofy.link_manager import PresenterLinkManager
from cros.factory.goofy.link_manager import LinkDownError
from cros.factory.test import factory
from cros.factory.utils import dhcp_utils
from cros.factory.utils import net_utils

_LOCALHOST = '127.0.0.1'
_STANDALONE = 'standalone'

class LinkManagerTest(unittest.TestCase):

  def setUp(self):
    self.dut_link = None
    self.presenter_link = None
    self.hook = mox.MockAnything()

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

  def StartPresenter(self):
    self.dut_link = DUTLinkManager(check_interval=1,
                                   methods={'Echo1': self.Echo},
                                   connect_hook=self.hook.dut_connect,
                                   disconnect_hook=self.hook.dut_disconnect)
    self.dut_link.Start()

  def StopPresenter(self):
    self.dut_link.Stop()
    self.dut_link = None

  def StartDUT(self):
    self.presenter_link = PresenterLinkManager(
        check_interval=1, methods={
            'Echo': self.Echo
        },
        connect_hook=self.hook.presenter_connect,
        disconnect_hook=self.hook.presenter_disconnect)
    if self.dut_link:
      time.sleep(0.5)
      self.dut_link.OnDHCPEvent(_LOCALHOST, _STANDALONE)

  def StopDUT(self):
    self.presenter_link.Stop()
    self.presenter_link = None

  def testLink(self):
    # DUT and presenter are up
    self.hook.dut_connect(_LOCALHOST, _STANDALONE)
    self.hook.presenter_connect(_LOCALHOST)

    # DUT is down
    self.hook.dut_disconnect(_LOCALHOST)

    # DUT is back up
    self.hook.dut_connect(_LOCALHOST, _STANDALONE)
    self.hook.presenter_connect(_LOCALHOST)

    # DUT suspend/resume
    self.hook.dut_connect(_LOCALHOST, _STANDALONE)
    self.hook.presenter_connect(_LOCALHOST)

    # Glitch in DUT ping response
    self.hook.dut_disconnect(_LOCALHOST)
    self.hook.dut_connect(_LOCALHOST, _STANDALONE)
    self.hook.presenter_connect(_LOCALHOST)

    mox.Replay(self.hook)

    self.StartPresenter()
    time.sleep(0.5)
    self.StartDUT()
    time.sleep(0.5)

    self.dut_link.Kick()

    time.sleep(0.2)
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsAlive())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.presenter_link.Echo1(10), 10)

    self.StopDUT()
    time.sleep(1.5)
    self.assertFalse(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertRaises(LinkDownError, lambda: self.dut_link.Echo('test'))
    self.StartDUT()
    time.sleep(1.5)
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsAlive())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.presenter_link.Echo1(10), 10)

    # Should not call disconnect hook if monitoring is stopped
    self.dut_link.SuspendMonitoring(3, _LOCALHOST)
    self.StopDUT()
    time.sleep(1.5)
    self.StartDUT()
    time.sleep(1.5)
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsAlive())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.presenter_link.Echo1(10), 10)

    # A glitch in DUT ping response
    self.presenter_link.StopPingServer()
    time.sleep(1.5)
    self.presenter_link.StartPingServer()
    time.sleep(1.5)
    self.assertTrue(self.dut_link.DUTIsAlive(_LOCALHOST))
    self.assertTrue(self.presenter_link.PresenterIsAlive())

    mox.Verify(self.hook)

if __name__ == '__main__':
  factory.init_logging()
  unittest.main()
