#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy_split import link_manager
from cros.factory.goofy_split.link_manager import DUTLinkManager
from cros.factory.goofy_split.link_manager import HostLinkManager
from cros.factory.goofy_split.link_manager import LinkDownError
from cros.factory.utils import test_utils

class LinkManagerTest(unittest.TestCase):
  def setUp(self):
    self.dut_link = None
    self.host_link = None
    self.hook = mox.MockAnything()

    link_manager.HOST_LINK_RPC_PORT = test_utils.FindUnusedTCPPort()
    link_manager.DUT_LINK_RPC_PORT = test_utils.FindUnusedTCPPort()

  def tearDown(self):
    if self.dut_link:
      self.dut_link.Stop()
    if self.host_link:
      self.host_link.Stop()

  def Echo(self, s):
    return s

  def StartHost(self):
    self.dut_link = DUTLinkManager(check_interval=1,
                                   methods={'Echo1': self.Echo},
                                   connect_hook=self.hook.dut_connect,
                                   disconnect_hook=self.hook.dut_disconnect)

  def StopHost(self):
    self.dut_link.Stop()
    self.dut_link = None

  def StartDUT(self):
    self.host_link = HostLinkManager(check_interval=1,
                                     methods={'Echo': self.Echo},
                                     connect_hook=self.hook.host_connect,
                                     disconnect_hook=self.hook.host_disconnect)

  def StopDUT(self):
    self.host_link.Stop()
    self.host_link = None

  def testLink(self):
    # DUT and host are up
    self.hook.dut_connect()
    self.hook.host_connect()

    # DUT is down
    self.hook.dut_disconnect()

    # DUT is back up
    self.hook.dut_connect()
    self.hook.host_connect()

    # Host is down
    self.hook.host_disconnect()

    # Host is back up
    self.hook.dut_connect()
    self.hook.host_connect()

    mox.Replay(self.hook)

    self.StartDUT()
    self.StartHost()

    time.sleep(0.5)

    self.dut_link.Kick()

    time.sleep(0.2)
    self.assertTrue(self.dut_link.DUTIsAlive())
    self.assertTrue(self.host_link.HostIsAlive())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.host_link.Echo1(10), 10)

    self.StopDUT()
    time.sleep(1.5)
    self.assertFalse(self.dut_link.DUTIsAlive())
    self.assertRaises(LinkDownError, lambda: self.dut_link.Echo('test'))
    self.StartDUT()
    time.sleep(1.5)
    self.assertTrue(self.dut_link.DUTIsAlive())
    self.assertTrue(self.host_link.HostIsAlive())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.host_link.Echo1(10), 10)

    self.StopHost()
    time.sleep(1.5)
    self.assertFalse(self.host_link.HostIsAlive())
    self.assertRaises(LinkDownError, lambda: self.host_link.Echo1('test'))
    self.StartHost()
    time.sleep(1.5)
    self.assertTrue(self.dut_link.DUTIsAlive())
    self.assertTrue(self.host_link.HostIsAlive())
    self.assertEqual(self.dut_link.Echo('test'), 'test')
    self.assertEqual(self.host_link.Echo1(10), 10)

    mox.Verify(self.hook)

if __name__ == '__main__':
  unittest.main()
