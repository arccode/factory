#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import httplib
import logging
import subprocess
import threading
import ws4py

from hashlib import sha1
from ws4py.websocket import WebSocket

from cros.factory.test import factory
from cros.factory.test.event import Event
from cros.factory.test.event import EventClient


class WebSocketManager(object):
  '''Object to manage web sockets for Goofy.

  Brokers between events in the event client infrastructure
  and on web sockets.  Also tails the console log and sends
  events on web sockets when new bytes become available.

  Each Goofy instance is associated with a UUID.  When a new web
  socket is created, we send a hello event on the socket with the
  current UUID.  If we receive a keepalive event with the wrong
  UUID, we disconnect the client.  This insures that we are always
  talking to a client that has a complete picture of our state
  (i.e., if the server restarts, the client must restart as well).
  '''
  def __init__(self, uuid):
    self.uuid = uuid
    self.lock = threading.Lock()
    self.web_sockets = set()
    self.event_client = None
    self.tail_process = None
    self.has_confirmed_socket = threading.Event()

    self.event_client = EventClient(callback=self._handle_event,
                    name='WebSocketManager')
    self.tail_process = subprocess.Popen(
      ["tail", "-F", factory.CONSOLE_LOG_PATH],
      stdout=subprocess.PIPE,
      close_fds=True)
    self.tail_thread = threading.Thread(target=self._tail_console)
    self.tail_thread.start()
    self.closed = False

  def close(self):
    with self.lock:
      if self.closed:
        return
      self.closed = True

    if self.event_client:
      self.event_client.close()
      self.event_client = None

    with self.lock:
      web_sockets = list(self.web_sockets)
    for web_socket in web_sockets:
      web_socket.close_connection()

    if self.tail_process:
      self.tail_process.kill()
      self.tail_process.wait()
    if self.tail_thread:
      self.tail_thread.join()

  def has_sockets(self):
    '''Returns true if any web sockets are currently connected.'''
    with self.lock:
      return len(self.web_sockets) > 0

  def handle_web_socket(self, request):
    '''Runs a web socket in the current thread.

    request: A RequestHandler object containing the request.
    '''
    def send_error(msg):
      logging.error('Unable to start WebSocket connection: %s', msg)
      request.send_response(400, msg)

    encoded_key = request.headers.get('Sec-WebSocket-Key')

    if (request.headers.get('Upgrade') != 'websocket' or
      request.headers.get('Connection') != 'Upgrade' or
      not encoded_key):
      send_error('Missing/unexpected headers in WebSocket request')
      return

    key = base64.b64decode(encoded_key)
    # Make sure the key is 16 characters, as required by the
    # WebSockets spec (RFC6455).
    if len(key) != 16:
      send_error('Invalid key length')

    version = request.headers.get('Sec-WebSocket-Version')
    if not version or version not in [str(x) for x in ws4py.WS_VERSION]:
      send_error('Unsupported WebSocket version %s' % version)
      return

    request.send_response(httplib.SWITCHING_PROTOCOLS)
    request.send_header('Upgrade', 'websocket')
    request.send_header('Connection', 'Upgrade')
    request.send_header(
      'Sec-WebSocket-Accept',
      base64.b64encode(sha1(encoded_key + ws4py.WS_KEY).digest()))
    request.end_headers()

    class MyWebSocket(WebSocket):
      def received_message(socket_self, message):
        event = Event.from_json(str(message))
        if event.type == Event.Type.KEEPALIVE:
          if event.uuid == self.uuid:
            if not self.has_confirmed_socket.is_set():
              logging.info('Chrome UI has come up')
            self.has_confirmed_socket.set()
          else:
            logging.warning('Disconnecting web socket with '
                    'incorrect UUID')
            socket_self.close_connection()
        else:
          self.event_client.post_event(event)

    web_socket = MyWebSocket(sock=request.connection)

    # Add a per-socket lock to use for sending, since ws4py is not
    # thread-safe.
    web_socket.send_lock = threading.Lock()
    with web_socket.send_lock:
      web_socket.send(Event(Event.Type.HELLO,
                  uuid=self.uuid).to_json())

    try:
      with self.lock:
        self.web_sockets.add(web_socket)
      logging.info('Running web socket')
      web_socket.run()
      logging.info('Web socket closed gracefully')
    except:
      logging.exception('Web socket closed with exception')
    finally:
      with self.lock:
        self.web_sockets.discard(web_socket)

  def wait(self):
    '''Waits for one socket to connect successfully.'''
    self.has_confirmed_socket.wait()

  def _tail_console(self):
    '''Tails the console log, generating an event whenever a new
    line is available.

    We send this event only to web sockets (not to event clients
    in general) since only the UI is interested in these log
    lines.
    '''
    while True:
      line = self.tail_process.stdout.readline()
      if line == '':
        break
      self._handle_event(
        Event(Event.Type.LOG,
            message=line.rstrip("\n")))

  def _handle_event(self, event):
    '''Sends an event to each open WebSocket client.'''
    with self.lock:
      web_sockets = list(self.web_sockets)

    if not web_sockets:
      return

    event_json = event.to_json()
    for web_socket in web_sockets:
      try:
        with web_socket.send_lock:
          web_socket.send(event_json)
      except:
        logging.exception('Unable to send event on web socket')
