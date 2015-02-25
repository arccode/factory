# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import base64
import os
import signal
import threading

from ws4py.websocket import WebSocket

import factory_common
from cros.factory.test.web_socket_utils import WebSocketHandshake


_SHELL = os.getenv('SHELL') or '/bin/bash'
_BUFSIZ = 8192


class TerminalManager(object):
  """Object to manage Terminal service for goofy."""
  def handle_web_socket(self, request):
    if not WebSocketHandshake(request):
      return

    pid, fd = os.forkpty()
    if pid == 0:
      env = os.environ.copy()
      env['USER'] = os.getenv('USER') or 'root'
      env['HOME'] = os.getenv('HOME') or '/root'
      os.chdir(env['HOME'])
      os.execve(_SHELL, [_SHELL], env)

    class TerminalWebSocket(WebSocket):
      def __init__(self, fd, **kwargs):
        super(TerminalWebSocket, self).__init__(**kwargs)
        self._fd = fd

      def received_message(self, message):
        os.write(self._fd, str(message))

    ws = TerminalWebSocket(fd, sock=request.connection)
    t = threading.Thread(target=ws.run)
    t.daemon = True
    t.start()

    while True:
      try:
        ws.send(base64.b64encode(os.read(fd, _BUFSIZ)))
      except OSError:
        break

    os.kill(pid, signal.SIGTERM)
    os.wait()
