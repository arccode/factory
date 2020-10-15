# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import fcntl
import json
import logging
import os
import signal
import struct
import termios
import threading

from ws4py.websocket import WebSocket

from cros.factory.goofy.plugins import plugin
from cros.factory.test.utils.web_socket_utils import WebSocketHandshake
from cros.factory.utils import type_utils


_SHELL = os.getenv('SHELL', '/bin/bash')
_BUFSIZ = 8192
_CONTROL_START = 128
_CONTROL_END = 129


class Terminal(plugin.Plugin):
  @type_utils.Overrides
  def OnStart(self):
    terminal_manager = TerminalManager()
    self.goofy.goofy_server.AddHTTPGetHandler(
        '/pty', terminal_manager.handle_web_socket)


class TerminalManager:
  """Object to manage Terminal service for goofy."""
  def handle_web_socket(self, request):
    if not WebSocketHandshake(request):
      return

    pid, fd = os.forkpty()
    if pid == 0:
      env = os.environ.copy()
      env['USER'] = os.getenv('USER', 'root')
      env['HOME'] = os.getenv('HOME', '/root')
      os.chdir(env['HOME'])
      os.execve(_SHELL, [_SHELL], env)

    class TerminalWebSocket(WebSocket):
      def __init__(self, fd, **kwargs):
        super(TerminalWebSocket, self).__init__(**kwargs)
        self._fd = fd
        self._control_state = None
        self._control_string = ''

      def HandlePTYControl(self, fd, control_string):
        msg = json.loads(control_string)
        command = msg['command']
        params = msg['params']
        if command == 'resize':
          # some error happened on websocket
          if len(params) != 2:
            return
          winsize = struct.pack('HHHH', params[0], params[1], 0, 0)
          fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        else:
          logging.warning('Invalid request command "%s"', command)

      def received_message(self, message):
        if message.is_text:
          if self._control_state:
            self._control_string += str(message)
          else:
            os.write(self._fd, str(message).encode('utf-8'))
        elif message.is_binary:
          # The control section is
          # binary(_CONTROL_START)-text-binary(_CONTROL_END)
          # So we only can receive length 1 binary message one time.
          if len(message) != 1:
            # skip it
            logging.warning('Len of binary message is %d, not 1.', len(message))
            return
          if self._control_state:
            if _CONTROL_END == message.data[0]:
              self.HandlePTYControl(self._fd, self._control_string)
              self._control_state = None
              self._control_string = ''
            else:
              logging.warning('Unexpected control message %d', message.data[0])
          else:
            if _CONTROL_START == message.data[0]:
              self._control_state = _CONTROL_START
            else:
              logging.warning('Unexpected control message %d', message.data[0])

    ws = TerminalWebSocket(fd, sock=request.connection)
    t = threading.Thread(target=ws.run)
    t.daemon = True
    t.start()

    while True:
      try:
        data = os.read(fd, _BUFSIZ)
        if data is not None:
          ws.send(base64.b64encode(data))
      except OSError:
        break

    os.kill(pid, signal.SIGTERM)
    os.wait()
