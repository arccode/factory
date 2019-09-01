#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import json
import logging
import StringIO
import unittest
import urllib2

import mox
from ws4py.client.threadedclient import WebSocketClient

import factory_common  # pylint: disable=unused-import
from cros.factory.tools import chrome_debugger


class ChromeRemoteDebuggerTest(unittest.TestCase):

  def setUp(self):
    self.chrome = chrome_debugger.ChromeRemoteDebugger()
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(urllib2, "urlopen")
    self.mox.StubOutWithMock(chrome_debugger, "WebSocketClient")
    self.mock_pageset_url = chrome_debugger.DEFAULT_CHROME_DEBUG_URL + "/json"
    self.mock_pageset = [{
        "id": "6CA5278B-EEC7-48F7-BBE2-297C6DEFB59A",
        "title": "FactoryTestExtension",
        "type": "background_page",
        "url": "chrome-extension://pngocaclmlmihmhokaeejfiklacihcmb/....html",
        "webSocketDebuggerUrl": "ws://6CA5278B-EEC7-48F7-BBE2-297C6DEFB59A"
    }, {
        "id": "79589549-AD32-4AC8-B4EE-6B06EFF2D7CF",
        "title": "Blank page",
        "type": "other",
        "url": "about:blank",
        "webSocketDebuggerUrl": "ws://79589549-AD32-4AC8-B4EE-6B06EFF2D7CF",
    }, {
        "id": "7711AF2B-B1CF-40C4-B269-0D29A72BEBBC",
        "title": "Why Should I Care What Color the Bikeshed Is?",
        "type": "other",
        "url": "http://cyan.bikeshed.com/",
        "webSocketDebuggerUrl": "ws://7711AF2B-B1CF-40C4-B269-0D29A72BEBBC"
    }]
    self.mock_pageset_stream = StringIO.StringIO(json.dumps(self.mock_pageset))
    self.mock_websocket = self.mox.CreateMock(WebSocketClient)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testIsReady(self):
    urllib2.urlopen(self.mock_pageset_url).AndRaise(
        urllib2.URLError("Cannot connect"))
    urllib2.urlopen(self.mock_pageset_url).AndReturn(self.mock_pageset_stream)
    self.mox.ReplayAll()
    self.assertFalse(self.chrome.IsReady())
    self.assertTrue(self.chrome.IsReady())
    self.mox.VerifyAll()

  def testGetPages(self):
    urllib2.urlopen(self.mock_pageset_url).AndReturn(self.mock_pageset_stream)
    urllib2.urlopen(self.mock_pageset_url).AndReturn(self.mock_pageset_stream)
    urllib2.urlopen(self.mock_pageset_url).AndReturn(self.mock_pageset_stream)
    self.mox.ReplayAll()
    self.assertEquals(self.chrome.GetPages(), self.mock_pageset)
    self.mock_pageset_stream.seek(0)
    self.assertEquals(self.chrome.GetPages("background_page"),
                      [self.mock_pageset[0]])
    self.mock_pageset_stream.seek(0)
    self.assertEquals(self.chrome.GetPages("no-such-page"), [])
    self.mox.VerifyAll()

  def testSetActivePage(self):
    self.mox.StubOutWithMock(self.chrome, "GetPages")
    self.chrome.GetPages("other").AndReturn(self.mock_pageset[1:])
    chrome_debugger.WebSocketClient(
        self.mock_pageset[1]["webSocketDebuggerUrl"]).AndReturn(
            self.mock_websocket)
    self.mock_websocket.connect()
    self.mock_websocket.close()
    self.mox.ReplayAll()

    self.chrome.SetActivePage()
    self.chrome.SetActivePage(None)
    self.mox.VerifyAll()

  def testSendCommand(self):
    command = {"method": "test", "params": {"param1": "value1"}}
    expected = command.copy()
    expected.update({"id": 1})
    self.chrome.active_websocket = self.mock_websocket
    self.chrome.active_websocket.send(json.dumps(expected))
    self.mox.ReplayAll()

    self.assertEquals(1, self.chrome.id)
    self.chrome.SendCommand(command)
    self.assertEquals(2, self.chrome.id)
    self.chrome.active_websocket = None
    self.mox.VerifyAll()

  def testPageNavigate(self):
    url = "http://blah"
    expected = {"method": "Page.navigate", "params": {"url": url}}
    expected.update({"id": 1})
    self.chrome.active_websocket = self.mock_websocket
    self.chrome.active_websocket.send(json.dumps(expected))
    self.mox.ReplayAll()

    self.chrome.PageNavigate(url)
    self.chrome.active_websocket = None
    self.mox.VerifyAll()


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  unittest.main()
