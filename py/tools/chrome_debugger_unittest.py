#!/usr/bin/env python3
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from io import StringIO
import json
import logging
import unittest
from unittest import mock
import urllib.error
import urllib.request

from ws4py.client.threadedclient import WebSocketClient

from cros.factory.tools import chrome_debugger


class ChromeRemoteDebuggerTest(unittest.TestCase):

  def setUp(self):
    self.chrome = chrome_debugger.ChromeRemoteDebugger()
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
    self.mock_pageset_stream = StringIO(json.dumps(self.mock_pageset))
    self.mock_websocket = mock.Mock(WebSocketClient)

  @mock.patch('urllib.request.urlopen')
  def testIsReady(self, urlopen_mock):
    urlopen_mock.side_effect = urllib.error.URLError("Cannot connect")
    self.assertFalse(self.chrome.IsReady())

    # TODO(kerker) Use urlopen_mock.reset_mock(side_effect=True) in py3
    urlopen_mock.side_effect = None
    urlopen_mock.return_value = self.mock_pageset_stream
    self.assertTrue(self.chrome.IsReady())
    urlopen_mock.assert_called_with(self.mock_pageset_url)

  @mock.patch('urllib.request.urlopen')
  def testGetPages(self, urlopen_mock):
    urlopen_mock.return_value = self.mock_pageset_stream
    self.assertEqual(self.chrome.GetPages(), self.mock_pageset)
    urlopen_mock.assert_called_with(self.mock_pageset_url)

    urlopen_mock.reset_mock()
    self.mock_pageset_stream.seek(0)
    self.assertEqual(self.chrome.GetPages("background_page"),
                     [self.mock_pageset[0]])
    urlopen_mock.assert_called_with(self.mock_pageset_url)

    urlopen_mock.reset_mock()
    self.mock_pageset_stream.seek(0)
    self.assertEqual(self.chrome.GetPages("no-such-page"), [])
    urlopen_mock.assert_called_with(self.mock_pageset_url)

  @mock.patch('cros.factory.tools.chrome_debugger.WebSocketClient')
  def testSetActivePage(self, web_socket_client_mock):
    self.chrome.GetPages = mock.Mock(return_value=self.mock_pageset[1:])
    web_socket_client_mock.return_value = self.mock_websocket
    self.mock_websocket.connect()
    self.mock_websocket.close()

    self.chrome.SetActivePage()
    self.chrome.SetActivePage(None)
    self.chrome.GetPages.assert_called_once_with("other")
    web_socket_client_mock.assert_called_once_with(
        self.mock_pageset[1]["webSocketDebuggerUrl"])

  def testSendCommand(self):
    command = {"method": "test", "params": {"param1": "value1"}}
    expected = command.copy()
    expected.update({"id": 1})
    self.chrome.active_websocket = self.mock_websocket

    self.assertEqual(1, self.chrome.id)

    self.chrome.SendCommand(command)
    self.assertEqual(2, self.chrome.id)
    self.chrome.active_websocket.send.assert_called_once_with(
        json.dumps(expected))
    self.chrome.active_websocket = None

  def testPageNavigate(self):
    url = "http://blah"
    expected = {"method": "Page.navigate", "params": {"url": url}}
    expected.update({"id": 1})
    self.chrome.active_websocket = self.mock_websocket

    self.chrome.PageNavigate(url)
    self.chrome.active_websocket.send.assert_called_once_with(
        json.dumps(expected))
    self.chrome.active_websocket = None


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  unittest.main()
