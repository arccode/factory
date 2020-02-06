# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import logging
import os
import subprocess
import threading
import time

from ws4py.websocket import WebSocket

from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test.event import ThreadingEventClient
from cros.factory.test import session
from cros.factory.test.utils.web_socket_utils import WebSocketHandshake
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import string_utils


# Number of lines to buffer for new clients.
TAIL_BUFFER_SIZE = 10


class WebSocketManager:
  """Object to manage web sockets for Goofy.

  Brokers between events in the event client infrastructure
  and on web sockets.  Also tails the console log and sends
  events on web sockets when new bytes become available.

  Each Goofy instance is associated with a UUID.  When a new web
  socket is created, we send a hello event on the socket with the
  current UUID.  If we receive a keepalive event with the wrong
  UUID, we disconnect the client.  This insures that we are always
  talking to a client that has a complete picture of our state
  (i.e., if the server restarts, the client must restart as well).

  Properties:
    tail_buffer: A rotating buffer of the last TAIL_BUFFER_SIZE lines,
        to give to new web clients.
  """

  def __init__(self, uuid):
    self.uuid = uuid
    self.lock = threading.Lock()
    self.web_sockets = set()
    self.event_client = None
    self.tail_process = None
    self.has_confirmed_socket = threading.Event()

    self.event_client = ThreadingEventClient(callback=self._handle_event,
                                             name='WebSocketManager')

    if not os.path.exists(paths.CONSOLE_LOG_PATH):
      file_utils.TryMakeDirs(os.path.dirname(paths.CONSOLE_LOG_PATH))
      # There's a small chance of race condition. Some data might already
      # flushed to console log before the 'TouchFile' got executed.
      # But it's fine though, since TouchFile() uses 'a' append mode.
      file_utils.TouchFile(paths.CONSOLE_LOG_PATH)
    self.tail_process = process_utils.Spawn(
        ['tail', '-F', paths.CONSOLE_LOG_PATH],
        ignore_stdin=True,
        stdout=subprocess.PIPE)
    self.tail_thread = threading.Thread(target=self._tail_console)
    self.closed = False
    self.tail_buffer = collections.deque()
    self.tail_thread.start()

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
    """Returns true if any web sockets are currently connected."""
    with self.lock:
      return len(self.web_sockets) > 0

  def handle_web_socket(self, request):
    """Runs a web socket in the current thread.

    request: A RequestHandler object containing the request.
    """
    if not WebSocketHandshake(request):
      return

    class MyWebSocket(WebSocket):

      def __init__(self, **kwargs):
        # Add a per-socket lock to use for sending, since ws4py is not
        # thread-safe.
        self.send_lock = threading.Lock()
        super(MyWebSocket, self).__init__(**kwargs)

      def received_message(socket_self, message):
        # pylint: disable=no-self-argument
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

    with self.lock:
      lines = list(self.tail_buffer)

    with web_socket.send_lock:
      web_socket.send(Event(Event.Type.HELLO,
                            uuid=self.uuid).to_json())
      for line in lines:
        # Send the last n lines.
        web_socket.send(
            Event(Event.Type.LOG,
                  message=string_utils.DecodeUTF8(line)).to_json())

    try:
      with self.lock:
        self.web_sockets.add(web_socket)
      logging.info('Running web socket')
      web_socket.run()
      logging.info('Web socket closed gracefully')
    except Exception:
      logging.exception('Web socket closed with exception')
    finally:
      with self.lock:
        self.web_sockets.discard(web_socket)
        if not self.web_sockets:
          self.has_confirmed_socket.clear()

  def wait(self):
    """Waits for one socket to connect successfully."""
    count = 1
    interval = 20
    # Wait at most interval seconds at a time; without a timeout, this seems
    # to eat SIGINT signals.
    while not self.has_confirmed_socket.wait(interval):
      # For some unknown reason, sometimes chrome UI does not come up and show
      # a white screen or this site can't be reached on the screen. Restarting
      # UI can solve this. See b/147780638 and b/176268649 for more contexts.
      # TODO(cyueh) Find why UI does not come up.
      logging.info('Wait web socket for %f seconds, restart ui',
                   interval * count)
      process_utils.Spawn(['restart', 'ui'], check_call=True,
                          log_stderr_on_error=True)
      count += 1

  def _tail_console(self):
    """Tails the console log, generating an event whenever a new
    line is available.

    We send this event only to web sockets (not to event clients
    in general) since only the UI is interested in these log
    lines.
    """
    # tail seems to have a bug where, when outputting to a pipe, it
    # doesn't output the first batch of data until it receives some
    # new output.  Let tail start up, then output a single line to
    # wake it up.  This is a terrible hack, but it's better than
    # missing a bunch of lines.  A better fix might involve emulating
    # tail directly in Python.
    def target():
      time.sleep(0.5)
      session.console.info('Opened console.')
    process_utils.StartDaemonThread(target=target)

    while True:
      line = self.tail_process.stdout.readline()
      if line == '':
        break
      with self.lock:
        self.tail_buffer.append(line)
        while len(self.tail_buffer) > TAIL_BUFFER_SIZE:
          self.tail_buffer.popleft()
      self._handle_event(
          Event(Event.Type.LOG,
                message=string_utils.DecodeUTF8(line).rstrip('\n')))

  def _handle_event(self, event):
    """Sends an event to each open WebSocket client."""
    with self.lock:
      web_sockets = list(self.web_sockets)

    if not web_sockets:
      if event.type == Event.Type.STATE_CHANGE:
        logging.info('No web socket gets %r', event)
      return

    event_json = event.to_json()
    missing_any_web_socket = False
    for web_socket in web_sockets:
      try:
        with web_socket.send_lock:
          web_socket.send(event_json)
      except Exception:
        missing_any_web_socket = True
        logging.exception('Unable to send event on web socket')
    if missing_any_web_socket:
      logging.info("Some web socket didn't get %r", event)
