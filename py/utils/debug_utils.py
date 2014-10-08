# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Debug utilities."""


from __future__ import print_function

import logging
import os
import sys
import threading
import time
import traceback
import SocketServer

import factory_common  # pylint: disable=W0611
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils

def DumpStackTracebacks():
  """Prints all threads' stack traces.

  Returns:
    The tracebacks of all threads.
  """
  results = []
  id_name_map = {}
  for thread in threading.enumerate():
    id_name_map[thread.ident] = thread.name

  results.append(
      '*****\n'
      '*\n'
      '* Dumping debug information.\n'
      '*\n'
      '*****\n')
  # pylint: disable=W0212
  for thread_id, stack in sys._current_frames().items():
    results.append('Thread %s (id=%d):\n' %
                   (id_name_map.get(thread_id, 'unnamed-%d' % thread_id),
                    thread_id))
    for filename, line_no, function_name, text in (
        traceback.extract_stack(stack)):
      # Same format as the usual Python stack trace, but indented
      # twice
      results.append('  File: "%s", line %d, in %s\n' % (
          filename, line_no, function_name))
      if text:
        results.append('    %s\n' % text.strip())

  results.append('***** End of debug information.\n')

  return ''.join(results)


class DebugRequestHandler(SocketServer.StreamRequestHandler):
  """Prints all threads' stack traces."""
  def handle(self):
    self.wfile.write(DumpStackTracebacks())

def StartDebugServer(address=net_utils.LOCALHOST, port=5339):
  """Opens a TCP server to print debug information.

  Returns the server and thread.
  """
  SocketServer.ThreadingTCPServer.allow_reuse_address = True
  server = SocketServer.ThreadingTCPServer(
      (address, port), DebugRequestHandler)
  thread = process_utils.StartDaemonThread(target=server.serve_forever,
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


def CatchException(name, enable=True):
  """Returns a decorator who catches exception and print certain name.

  This is useful in functions of goofy managers where we want to catch
  the exception happened in managers and make sure the error will not
  break its user(goofy).

  Args:
    name: The name of function or class that should be printed in
      warning message.
    enable: True to enable this decorator. This is useful in unittest
      of the user where we really want to verify the function of decorated
      functions.

  Returns:
    A decorater method that will catch exceptions and only logs reduced
    trace with name.
  """
  def _CatchExceptionDecorator(method):
    """A decorator who catches exception from method.

    Args:
      method: The method that needs to be decorated.

    Returns:
      A decorated method that will catch exceptions and only logs reduced
      trace.
    """
    def Wrap(*args, **kwargs):
      try:
        method(*args, **kwargs)
      except:  # pylint: disable=W0702
        logging.warning(
          '%s Exception: %s.', name,
          '\n'.join(traceback.format_exception_only(
              *sys.exc_info()[:2])).strip())
    return Wrap if enable else method
  return _CatchExceptionDecorator


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  StartDebugServer()
  time.sleep(86400)
