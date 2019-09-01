#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Chrome remote debugging protocol.

This module provides controlling Chrome browser by the Remote Debugging
Protocol.

Example:

  To change current tab to Google,

  chrome = ChromeRemoteDebugger()
  while not chrome.IsReady():
    time.sleep(1)
  chrome.SetActivePage()
  chrome.PageNavigate('http://www.google.com')

See https://developer.chrome.com/devtools/docs/debugger-protocol for more
information."""


from __future__ import print_function

import json
import sys
import threading
import urllib2

from ws4py.client.threadedclient import WebSocketClient


DEFAULT_CHROME_DEBUG_URL = 'http://127.0.0.1:9222'


class ChromeRemoteDebugger(object):
  """An interface to control Chrome brower by remote debugging protocol.

  Args:
    debug_url: An URL to connect to debug port (--remote-debugging-port) of
               running Chrome instance.

  Attributes:
    id: An incremental identifier for debugging protocol.
    lock: Internal lock.
    active_websocket: An websocket client to active page.
  """

  ANY = 'any value'

  def __init__(self, debug_url=DEFAULT_CHROME_DEBUG_URL):
    self.debug_url = debug_url
    self.id = 1
    self.active_websocket = None
    self.lock = threading.Lock()

  def IsReady(self):
    """Checks if a browser instance is available (with debugging ports enabled).

    Returns:
      True if an instance is ready, otherwise False.
    """
    with self.lock:
      if self.active_websocket:
        return True
    try:
      self.GetPages()
      return True
    except Exception:
      return False

  def GetPages(self, page_type=ANY):
    """Returns current pages of running Chrome browser.

    Args:
      page_type: Filters result by given type, or ANY to return all types.

    Returns:
      A list representing PageSet in Chrome remote debugging protocol.
    """
    page_set = json.load(urllib2.urlopen(self.debug_url + '/json'))
    if page_type is not self.ANY:
      return [page for page in page_set if page['type'] == page_type]
    return page_set

  def SetActivePage(self, page=ANY):
    """Sets a page as active session for sending commands.

    Args:
      page: A page instance (returned by GetPages), or ANY to activate the first
            normal webpage (type 'other').
    """
    if page is self.ANY:
      page = self.GetPages('other')[0]
    ws = None
    if page is not None:
      ws = WebSocketClient(page['webSocketDebuggerUrl'])
      ws.connect()
    with self.lock:
      if self.active_websocket:
        self.active_websocket.close()
      self.active_websocket = ws

  def SendCommand(self, command):
    """Sends a remote debugging websocket command to Chrome browser.

    Args:
      command: A dictionary of remote debugging command.
    """
    command = command.copy()
    with self.lock:
      command.update({'id': self.id})
      self.id += 1
      self.active_websocket.send(json.dumps(command))

  def PageNavigate(self, url):
    """Navigates current page to the given URL.

    Args:
      url: An URL to open in browser.
    """
    self.SendCommand({'method': 'Page.navigate',
                      'params': {'url': url}})


if __name__ == '__main__':
  if len(sys.argv) != 3:
    exit('Usage: %s method_name json_params' % sys.argv[0])

  chrome = ChromeRemoteDebugger()
  pages = chrome.GetPages('page')
  # Pages with type 'page' contains page like "chrome://app-list", which we
  # don't want to redirect.
  targets = [p for p in pages if not p['url'].startswith('chrome://')]

  page_command = {'method': sys.argv[1], 'params': json.loads(sys.argv[2])}
  for target in targets:
    print("Send %s to page %s" % (page_command, target))
    chrome.SetActivePage(target)
    chrome.SendCommand(page_command)
