#!/usr/bin/python -u
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import logging
import threading
import uuid
from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler
from ws4py.websocket import WebSocket
from ws4py.client.threadedclient import WebSocketClient

import factory_common  # pylint: disable=W0611
from cros.factory.test import state
from cros.factory.test.utils import Enum
from cros.factory.test.web_socket_utils import WebSocketHandshake


# Standard web socket port.  This may be replaced by unit tests.
UI_APP_CONTROLLER_PORT = 4010

# The commands that UI presenter app accepts.
UI_APP_COMMAND = Enum(['CONNECT', 'DISCONNECT', 'INFO', 'ERROR',
                       'START_COUNTDOWN', 'STOP_COUNTDOWN'])


class UIAppControllerHandler(SimpleHTTPRequestHandler):

  def do_GET(self):
    WebSocketHandshake(self)
    web_socket = WebSocket(sock=self.connection)
    web_socket.received_message = self.server.controller.ReceivedMessage
    try:
      self.server.controller.AddWebSocket(web_socket)
      web_socket.run()
    except:  # pylint: disable=W0702
      logging.exception('Web socket closed with exception')
    finally:
      self.server.controller.DiscardWebSocket(web_socket)


class UIAppController(object):

  def __init__(self, connect_hook=None, disconnect_hook=None):
    self.web_sockets = set()
    self._connect_hook = connect_hook
    self._disconnect_hook = disconnect_hook
    self._connect_event = threading.Event()
    self._abort_event = threading.Event()
    self._last_msg = None
    self._msg_event = threading.Event()
    self.lock = threading.Lock()
    self.httpd = HTTPServer(('0.0.0.0', UI_APP_CONTROLLER_PORT),
                            UIAppControllerHandler)
    self.httpd.controller = self
    self.httpd_thread = threading.Thread(target=self.ServeHTTPForever)
    self.httpd_thread.start()

  def ServeHTTPForever(self):
    while not self._abort_event.isSet():
      self.httpd.handle_request()
    # We're done. Make sure the port is freed.
    del self.httpd

  def Stop(self):
    self._abort_event.set()
    # Kick httpd thread so that it aborts
    client = WebSocketClient('ws://127.0.0.1:%d' % UI_APP_CONTROLLER_PORT)
    client.connect()
    client.close()

  def AddWebSocket(self, ws):
    with self.lock:
      self.web_sockets.add(ws)
      self._connect_event.set()
    if self._connect_hook is not None and not self._abort_event.isSet():
      self._connect_hook()

  def DiscardWebSocket(self, ws):
    with self.lock:
      self.web_sockets.discard(ws)
    if self._disconnect_hook is not None and not self._abort_event.isSet():
      self._disconnect_hook()

  def WaitForWebSocket(self):
    self._connect_event.wait()

  def HasWebSockets(self):
    return bool(self.web_sockets)

  def SendMessage(self, msg):
    msg_string = json.dumps(msg)
    with self.lock:
      for ws in self.web_sockets:
        ws.send(msg_string)

  def ReceivedMessage(self, msg):
    # Some websocket client appends newline (\n) after the message.
    # To be safe, let's strip the incoming message.
    self._last_msg = str(msg).strip()
    self._msg_event.set()

  def ShowUI(self, dut_ip, dut_uuid=None):
    # If dut_uuid is not specified, generate one in the same format
    # as jsonrpc_utils:GetUuid.
    if not dut_uuid:
      dut_uuid = str(uuid.uuid4())
    url = 'http://%s:%d/' % (dut_ip, state.DEFAULT_FACTORY_STATE_PORT)
    self.SendMessage({'command': UI_APP_COMMAND.CONNECT,
                      'url': url, 'uuid': dut_uuid})
    # Wait for the UI presenter app to acknowledge
    if not self._msg_event.wait(timeout=5):
      return False
    self._msg_event.clear()
    return self._last_msg == "OK"

  def ShowDisconnectedScreen(self):
    self.SendMessage({'command': UI_APP_COMMAND.DISCONNECT})

  def ShowInfoMessage(self, msg):
    self.SendMessage({'command': UI_APP_COMMAND.INFO, 'str': msg})

  def ShowErrorMessage(self, msg):
    self.SendMessage({'command': UI_APP_COMMAND.ERROR, 'str': msg})

  def StartCountdown(self, msg, timeout, end_msg, end_msg_color):
    self.SendMessage({'command': UI_APP_COMMAND.START_COUNTDOWN,
                      'message': msg,
                      'timeout': timeout,
                      'end_message': end_msg,
                      'end_message_color': end_msg_color})

  def StopCountdown(self):
    self.SendMessage({'command': UI_APP_COMMAND.STOP_COUNTDOWN})
