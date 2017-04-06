#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import json
import mox
import threading
import unittest
from ws4py.client.threadedclient import WebSocketClient

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import ui_app_controller
from cros.factory.goofy.ui_app_controller import UIAppController
from cros.factory.utils import net_utils


class UIAppControllerTest(unittest.TestCase):

  def setUp(self):
    ui_app_controller.UI_APP_CONTROLLER_PORT = net_utils.FindUnusedTCPPort()
    self.hook = mox.MockAnything()
    self.connected_event = threading.Event()
    self.disconnected_event = threading.Event()
    self.controller = None
    self.client = None

  def StartControllerAndClient(self):
    self.controller = UIAppController(
        connect_hook=self.connected_event.set,
        disconnect_hook=self.disconnected_event.set)
    self.client = WebSocketClient('ws://127.0.0.1:%d' %
                                  ui_app_controller.UI_APP_CONTROLLER_PORT)
    self.client.received_message = self.ReceivedMessage

  def ReceivedMessage(self, message):
    self.hook.message(json.loads(str(message)))

  def SendOK(self, unused_cmd):
    self.client.send('OK\n')

  def SendError(self, unused_cmd):
    self.client.send('ERROR\n')

  def tearDown(self):
    if self.controller:
      self.controller.Stop()

  def testHook(self):
    self.hook.message({
        'url': 'http://10.3.0.11:4012/',
        'command': 'CONNECT',
        'dongle_mac_address': 'unittest'
    }).WithSideEffects(self.SendError)
    self.hook.message({
        'url': 'http://10.3.0.11:4012/',
        'command': 'CONNECT',
        'dongle_mac_address': 'unittest'
    }).WithSideEffects(self.SendOK)

    mox.Replay(self.hook)

    self.StartControllerAndClient()

    self.client.connect()
    self.assertTrue(self.connected_event.wait(0.2))

    self.assertFalse(self.controller.ShowUI('10.3.0.11', 'unittest'))
    self.assertTrue(self.controller.ShowUI('10.3.0.11', 'unittest'))

    self.client.close()
    self.assertTrue(self.disconnected_event.wait(0.2))

    mox.Verify(self.hook)

if __name__ == '__main__':
  unittest.main()
