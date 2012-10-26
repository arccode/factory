# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import sys
import threading
import time
import traceback
import SocketServer

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils

class DebugRequestHandler(SocketServer.StreamRequestHandler):
  """Prints all threads' stack traces."""
  def handle(self):
    id_name_map = {}
    for thread in threading.enumerate():
      id_name_map[thread.ident] = thread.name

    self.wfile.write(
        '*****\n'
        '*\n'
        '* Dumping debug information.\n'
        '*\n'
        '*****\n')
    # pylint: disable=W0212
    for thread_id, stack in sys._current_frames().items():
      self.wfile.write('Thread %s (id=%d):\n' %
                       (id_name_map.get(thread_id, 'unnamed-%d' % thread_id),
                        thread_id))
      for filename, line_no, function_name, text in (
          traceback.extract_stack(stack)):
        # Same format as the usual Python stack trace, but indented
        # twice
        self.wfile.write('  File: "%s", line %d, in %s\n' % (
            filename, line_no, function_name))
        if text:
          self.wfile.write('    %s\n' % text.strip())

    self.wfile.write('***** End of debug information.\n')


def StartDebugServer(address='localhost', port=5339):
  """Opens a TCP server to print debug information.

  Returns the server and thread."""
  SocketServer.ThreadingTCPServer.allow_reuse_address = True
  server = SocketServer.ThreadingTCPServer(
      (address, port), DebugRequestHandler)
  thread = utils.StartDaemonThread(target=server.serve_forever,
                                   name='tcp-debug-server')

  logging.info('Debug server started on %s:%d', address, port)
  return server, thread


def MaybeStartDebugServer():
  """Starts a debug server if the CROS_DEBUG_SERVER_PORT is set."""
  port = os.environ.get('CROS_DEBUG_SERVER_PORT')
  if port:
    return StartDebugServer(port=int(port))
  else:
    return None


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  StartDebugServer()
  time.sleep(86400)
