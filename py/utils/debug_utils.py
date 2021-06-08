# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Debug utilities."""

import functools
import inspect
import logging
import os
import socketserver
import sys
import threading
import time
import traceback

from . import net_utils
from . import process_utils
from . import sys_utils


def DumpStackTracebacks():
  """Collects all threads' stack traces.

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
  # pylint: disable=protected-access
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


def FormatExceptionOnly():
  """Formats the current exception string.

  Must only be called from inside an exception handler.

  Returns:
    A string representing the exception.
  """
  return '\n'.join(
      traceback.format_exception_only(*sys.exc_info()[:2])).strip()


class DebugRequestHandler(socketserver.StreamRequestHandler):
  """Prints all threads' stack traces."""

  def handle(self):
    self.wfile.write(DumpStackTracebacks())


def StartDebugServer(address=net_utils.LOCALHOST, port=5339):
  """Opens a TCP server to print debug information.

  Returns the server and thread.
  """
  socketserver.ThreadingTCPServer.allow_reuse_address = True
  server = socketserver.ThreadingTCPServer(
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
  return None


def CatchException(name, enable=True):
  """Returns a decorator that catches exceptions and logs them.

  This is useful in functions of goofy managers where we want to catch
  the exception that occurred within the manager, and make sure the error
  will not break its user (Goofy).

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
    """A decorator that catches exceptions from method.

    Args:
      method: The method that needs to be decorated.

    Returns:
      A decorated method that will catch exceptions and only logs reduced
      trace.
    """
    @functools.wraps(method)
    def Wrap(*args, **kwargs):
      try:
        return method(*args, **kwargs)
      except Exception:
        logging.warning(
            '%s Exception: %s.', name,
            '\n'.join(traceback.format_exception_only(
                *sys.exc_info()[:2])).strip())
    return Wrap if enable else method
  return _CatchExceptionDecorator


def SetupLogging(level=logging.WARNING, log_file_name=None):
  """Configure logging level, format, and target file/stream.

  Args:
    level: The logging.{DEBUG,INFO,etc} level of verbosity to show.
    log_file_name: File for appending log data.
  """
  logging.basicConfig(
      format='%(levelname)-8s %(asctime)-8s %(message)s',
      datefmt='%H:%M:%S',
      level=level,
      **({'filename': log_file_name} if log_file_name else {}))
  logging.Formatter.converter = time.gmtime
  logging.info(time.strftime('%Y.%m.%d %Z', time.gmtime()))


def GetCallerName(num_frame=1):
  """Get the name of function that calls current function.

  For example:
    def F():
      print GetCallerName()

    def G():
      F()

    G()  # output: G

  Args:
    num_frame: number of frames to go back, num_frame = 1 will returns name of
        caller, num_frame = 2 will returns name of caller's caller.

  Raises:
    ValueError if the frame is out of range of the current call stack.
  """
  frame = sys._getframe(num_frame + 1)  # pylint: disable=protected-access
  return inspect.getframeinfo(frame, 1)[2]


def NoRecursion(func):
  """Disallow recursive call on a function.

  Note that this is **function** based checking, therefore, the following
  example still count as recursion and will raise an exception::

      class A:
        @NoRecursion
        def func(self, other_a):
          if other_a:
            other_a.func(None)

      a = A()
      b = A()
      a.func(b)  # an exception will be raised
  """
  # pylint: disable=protected-access
  func._running_threads = []

  @functools.wraps(func)
  def Wrapped(*args, **kwargs):
    thread_id = threading.get_ident()
    if thread_id in func._running_threads and sys_utils.InChroot():
      logging.error('Detect unexpected recursion: \n%s', DumpStackTracebacks())
    assert thread_id not in func._running_threads, \
        'Recursion for %s is not allowed' % func.__name__
    try:
      func._running_threads.append(thread_id)
      return func(*args, **kwargs)
    finally:
      func._running_threads.remove(thread_id)

  return Wrapped


class DummyInterface:
  """A special class for providing dummy implementation."""

  def __init__(self, *args, **kargs):
    logging.debug('%s.%s%r%r', self.__class__.__name__, '__init__', args, kargs)

  def __getattr__(self, attr):
    def MockedMethod(*args, **kargs):
      logging.debug('%s.%s%r%r', self.__class__.__name__, attr, args, kargs)
    setattr(self, attr, MockedMethod)
    return MockedMethod


def GetInterface(interface, dummy_interface=DummyInterface, is_dummy=False):
  """Returns a real or dummy interface based on is_dummy.

  Args:
    interface: the constructor of real interface.
    dummy_interface: a constructor for dummy interface.
    is_dummy: True to request for dummy interface, otherwise real interface.

  Returns:
    dummy_interface if is_dummy is True, otherwise (real) interface.
  """
  return dummy_interface if is_dummy else interface


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  StartDebugServer()
  time.sleep(86400)
