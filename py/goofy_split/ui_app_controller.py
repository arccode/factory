#!/usr/bin/python -u
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import threading
from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler
from ws4py.websocket import WebSocket

import factory_common  # pylint: disable=W0611
from cros.factory.test import state
from cros.factory.utils.web_socket_utils import WebSocketHandshake


# Standard web socket port.  This may be replaced by unit tests.
UI_APP_CONTROLLER_PORT = 4010


class UIAppControllerHandler(SimpleHTTPRequestHandler):

  def do_GET(self):
    WebSocketHandshake(self)
    web_socket = WebSocket(sock=self.connection)
    try:
      self.server.controller.AddWebSocket(web_socket)
      web_socket.run()
    except:  # pylint: disable=W0702
      logging.exception('Web socket closed with exception')
    finally:
      self.server.controller.DiscardWebSocket(web_socket)


class UIAppController(object):

  def __init__(self):
    self.web_sockets = set()
    self._connect_event = threading.Event()
    self._abort_event = threading.Event()
    self.lock = threading.Lock()
    self.httpd = HTTPServer(('0.0.0.0', UI_APP_CONTROLLER_PORT),
                            UIAppControllerHandler)
    self.httpd.controller = self
    self.httpd_thread = threading.Thread(target=self.ServeHTTPForever)
    self.httpd_thread.start()

  def ServeHTTPForever(self):
    while not self._abort_event.isSet():
      self.httpd.handle_request()

  def Stop(self):
    self._abort_event.set()

  def AddWebSocket(self, ws):
    with self.lock:
      self.web_sockets.add(ws)
      self._connect_event.set()

  def DiscardWebSocket(self, ws):
    with self.lock:
      self.web_sockets.discard(ws)

  def WaitForWebSocket(self):
    self._connect_event.wait()

  def SendMessage(self, msg):
    with self.lock:
      for ws in self.web_sockets:
        ws.send(msg)

  def ShowUI(self, dut_ip):
    url = 'http://%s:%d/' % (dut_ip, state.DEFAULT_FACTORY_STATE_PORT)
    self.SendMessage(url)

  def ShowDisconnectedScreen(self):
    self.SendMessage('DISCONNECT')
