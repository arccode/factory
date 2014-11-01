#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import json
import mox
import time
import unittest
import uuid
from ws4py.client.threadedclient import WebSocketClient

import factory_common  # pylint: disable=W0611
from cros.factory.goofy_split import ui_app_controller
from cros.factory.goofy_split.ui_app_controller import UIAppController
from cros.factory.utils import test_utils

class UIAppControllerTest(unittest.TestCase):
  def setUp(self):
    ui_app_controller.UI_APP_CONTROLLER_PORT = test_utils.FindUnusedTCPPort()
    self.hook = mox.MockAnything()
    self.controller = None
    self.client = None

  def StartControllerAndClient(self):
    self.controller = UIAppController(connect_hook=self.hook.connect,
                                      disconnect_hook=self.hook.disconnect)
    self.client = WebSocketClient('ws://127.0.0.1:%d' %
                                  ui_app_controller.UI_APP_CONTROLLER_PORT)
    self.client.received_message = self.ReceivedMessage

  def ReceivedMessage(self, message):
    self.hook.message(json.loads('%s' % message))

  def SendOK(self, unused_cmd):
    self.client.send("OK\n")

  def SendError(self, unused_cmd):
    self.client.send("ERROR\n")

  def tearDown(self):
    if self.controller:
      self.controller.Stop()

  def testHook(self):
    this_uuid = str(uuid.uuid4())

    self.hook.connect()
    self.hook.message({'url': 'http://10.3.0.11:4012/', 'command': 'CONNECT',
                       'uuid': this_uuid}).WithSideEffects(self.SendError)
    self.hook.message({'url': 'http://10.3.0.11:4012/', 'command': 'CONNECT',
                       'uuid': this_uuid}).WithSideEffects(self.SendOK)
    self.hook.disconnect()

    mox.Replay(self.hook)

    self.StartControllerAndClient()

    self.client.connect()
    self.assertFalse(self.controller.ShowUI('10.3.0.11', dut_uuid=this_uuid))
    self.assertTrue(self.controller.ShowUI('10.3.0.11', dut_uuid=this_uuid))
    self.client.close()

    time.sleep(0.2) # Wait for WebSocket to close

    mox.Verify(self.hook)

if __name__ == '__main__':
  unittest.main()
