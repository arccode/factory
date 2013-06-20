# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cPickle as pickle
import errno
import json
import logging
import os
import socket
import SocketServer
import sys
import tempfile
import threading
import time
import traceback
import types
from Queue import Empty, Queue

import factory_common # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.unicode_to_string import UnicodeToString


# Environment variable storing the path to the endpoint.
CROS_FACTORY_EVENT = 'CROS_FACTORY_EVENT'

# Maximum allowed size for messages. If messages are bigger than this, they
# will be truncated by the seqpacket sockets.
_MAX_MESSAGE_SIZE = 65535

# Maximum size of logged event data in debug log. Sometimes a test may pass
# large data to JavaScript functions. If all of it is logged, it can easily take
# up all disk space.
_MAX_EVENT_SIZE_FOR_DEBUG_LOG = 512

# Hello message send by the server and expected as the first datagram by
# the client.
_HELLO_MESSAGE = '\1'

def json_default_repr(obj):
  '''Converts an object into a suitable representation for
  JSON-ification.

  If obj is an object, this returns a dict with all properties
  not beginning in '_'. Otherwise, the original object is
  returned.
  '''
  if isinstance(obj, object):
    return dict([(k,v) for k, v in obj.__dict__.iteritems()
           if k[0] != "_"])
  else:
    return obj


class Event(object):
  '''
  An event object that may be written to the event server.

  E.g.:

    event = Event(Event.Type.STATE_CHANGE,
           test='foo.bar',
           state=TestState(...))
  '''
  Type = type('Event.Type', (), {
      # The state of a test has changed.
      'STATE_CHANGE':     'goofy:state_change',
      # The UI has come up.
      'UI_READY':       'goofy:ui_ready',
      # Tells goofy to switch to a new test.
      'SWITCH_TEST':      'goofy:switch_test',
      # Tells goofy to rotate visibility to the next active test.
      'SHOW_NEXT_ACTIVE_TEST': 'goofy:show_next_active_test',
      # Tells goofy to show a particular test.
      'SET_VISIBLE_TEST':   'goofy:set_visible_test',
      # Tells goofy to clear all state and restart testing.
      'RESTART_TESTS': 'goofy:restart_tests',
      # Tells goofy to run all tests that haven't been run yet.
      'AUTO_RUN': 'goofy:auto_run',
      # Tells goofy to set all failed tests' state to untested and re-run.
      'RE_RUN_FAILED': 'goofy:re_run_failed',
      # Tells goofy to re-run all tests with particular statuses.
      'RUN_TESTS_WITH_STATUS': 'goofy:run_tests_with_status',
      # Clears state of all tests underneath the given path.
      'CLEAR_STATE': 'goofy:clear_state',
      # Tells goofy to go to the review screen.
      'REVIEW': 'goofy:review',
      # Tells the UI about a single new line in the log.
      'LOG': 'goofy:log',
      # A hello message to a new WebSocket. Contains a 'uuid' parameter
      # identification the particular invocation of the server.
      'HELLO': 'goofy:hello',
      # A keepalive message from the UI. Contains a 'uuid' parameter
      # containing the same 'uuid' value received when the client received
      # its HELLO.
      'KEEPALIVE': 'goofy:keepalive',
      # Initializes the test UI.
      'INIT_TEST_UI': 'goofy:init_test_ui',
      # Sets the UI in the test pane.
      'SET_HTML': 'goofy:set_html',
      # Runs JavaScript in the test pane.
      'RUN_JS': 'goofy:run_js',
      # Calls a JavaScript function in the test pane.
      'CALL_JS_FUNCTION': 'goofy:call_js_function',
      # Event from a test UI.
      'TEST_UI_EVENT': 'goofy:test_ui_event',
      # Message from the test UI that it has finished.
      'END_TEST': 'goofy:end_test',
      # Message to tell the test UI to destroy itself.
      'DESTROY_TEST': 'goofy:destroy_test',
      # Message telling Goofy should re-read system info.
      'UPDATE_SYSTEM_INFO': 'goofy:update_system_info',
      # Message containing new system info from Goofy.
      'SYSTEM_INFO': 'goofy:system_info',
      # Tells Goofy to stop all tests.
      'STOP': 'goofy:stop',
      # Indicates a pending shutdown.
      'PENDING_SHUTDOWN': 'goofy:pending_shutdown',
      # Cancels a pending shutdown.
      'CANCEL_SHUTDOWN': 'goofy:cancel_shutdown',
      # Tells UI to update notes.
      'UPDATE_NOTES': 'goofy:update_notes',
      })

  def __init__(self, type, **kw): # pylint: disable=W0622
    self.type = type
    self.timestamp = time.time()
    for k, v in kw.iteritems():
      setattr(self, k, v)

  def __repr__(self):
    return factory.std_repr(
      self,
      extra=[
        'type=%s' % self.type,
        'timestamp=%s' % time.ctime(self.timestamp)],
      excluded_keys=['type', 'timestamp'])

  def to_json(self):
    return json.dumps(self, default=json_default_repr)

  @staticmethod
  def from_json(encoded_event):
    kw = UnicodeToString(json.loads(encoded_event))
    type = kw.pop('type')
    return Event(type=type, **kw)

_unique_id_lock = threading.Lock()
_unique_id = 1
def get_unique_id():
  global _unique_id
  with _unique_id_lock:
    ret = _unique_id
    _unique_id += 1
  return ret


class EventServerRequestHandler(SocketServer.BaseRequestHandler):
  '''
  Request handler for the event server.

  This class is agnostic to message format (except for logging).
  '''
  # pylint: disable=W0201,W0212
  def setup(self):
    SocketServer.BaseRequestHandler.setup(self)
    threading.current_thread().name = (
      'EventServerRequestHandler-%d' % get_unique_id())
    # A thread to be used to send messages that are posted to the queue.
    self.send_thread = None
    # A queue containing messages.
    self.queue = Queue()

  def handle(self):
    # The handle() methods is run in a separate thread per client
    # (since EventServer has ThreadingMixIn).
    logging.debug('Event server: handling new client')
    try:
      self.server._subscribe(self.queue)

      # Send hello, now that we've subscribed.  Client will wait for
      # it before returning from the constructor.
      self.request.send(_HELLO_MESSAGE)

      self.send_thread = threading.Thread(
        target=self._run_send_thread,
        name='EventServerSendThread-%d' % get_unique_id())
      self.send_thread.daemon = True
      self.send_thread.start()

      # Process events: continuously read message and broadcast to all
      # clients' queues.
      while True:
        msg = self.request.recv(_MAX_MESSAGE_SIZE + 1)
        if len(msg) > _MAX_MESSAGE_SIZE:
          logging.error('Event server: message too large')
        if len(msg) == 0:
          break # EOF
        self.server._post_message(msg)
    except socket.error, e:
      if e.errno in [errno.ECONNRESET, errno.ESHUTDOWN]:
        pass # Client just quit
      else:
        raise e
    finally:
      logging.debug('Event server: client disconnected')
      self.queue.put(None) # End of stream; make writer quit
      self.server._unsubscribe(self.queue)

  def _run_send_thread(self):
    while True:
      message = self.queue.get()
      if message is None:
        return
      try:
        self.request.send(message)
      except: # pylint: disable=W0702
        return


class EventServer(SocketServer.ThreadingUnixStreamServer):
  '''
  An event server that broadcasts messages to all clients.

  This class is agnostic to message format (except for logging).
  '''
  allow_reuse_address = True
  socket_type = socket.SOCK_SEQPACKET
  daemon_threads = True

  def __init__(self, path=None):
    '''
    Constructor.

    @param path: Path at which to create a UNIX stream socket.
      If None, uses a temporary path and sets the CROS_FACTORY_EVENT
      environment variable for future clients to use.
    '''
    # A set of queues listening to messages.
    self._queues = set()
    # A lock guarding the _queues variable.
    self._lock = threading.Lock()
    if not path:
      path = tempfile.mktemp(prefix='cros_factory_event.')
      os.environ[CROS_FACTORY_EVENT] = path
      logging.info('Setting %s=%s', CROS_FACTORY_EVENT, path)
    SocketServer.UnixStreamServer.__init__( # pylint: disable=W0233
      self, path, EventServerRequestHandler)

  def _subscribe(self, queue):
    '''
    Subscribes a queue to receive events.

    Invoked only from the request handler.
    '''
    with self._lock:
      self._queues.add(queue)

  def _unsubscribe(self, queue):
    '''
    Unsubscribes a queue to receive events.

    Invoked only from the request handler.
    '''
    with self._lock:
      self._queues.discard(queue)

  def _post_message(self, message):
    '''
    Posts a message to all clients.

    Invoked only from the request handler.
    '''
    try:
      if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug('Event server: dispatching object %s',
               pickle.loads(message))
    except: # pylint: disable=W0702
      # Message isn't parseable as a pickled object; weird!
      logging.info(
        'Event server: dispatching message %r', message)

    with self._lock:
      for q in self._queues:
        # Note that this is nonblocking (even if one of the
        # clients is dead).
        q.put(message)


class EventClient(object):
  EVENT_LOOP_GOBJECT_IDLE = 'EVENT_LOOP_GOBJECT_IDLE'
  EVENT_LOOP_GOBJECT_IO = 'EVENT_LOOP_GOBJECT_IO'
  EVENT_LOOP_WAIT = 'EVENT_LOOP_WAIT'

  '''
  A client used to post and receive messages from an event server.

  All events sent through this class must be subclasses of Event. It
  marshals Event classes through the server by pickling them.
  '''
  def __init__(self, path=None, callback=None, event_loop=None, name=None):
    '''
    Constructor.

    @param path: The UNIX seqpacket socket endpoint path. If None, uses
      the CROS_FACTORY_EVENT environment variable.
    @param callback: A callback to call when events occur. The callback
      takes one argument: the received event.
    @param event_loop: An event loop to use to post the events. May be one
      of:

      - A Queue object, in which case a lambda invoking the callback is
        written to the queue.
      - EVENT_LOOP_GOBJECT_IDLE, in which case the callback will be
        invoked in the gobject event loop using idle_add.
      - EVENT_LOOP_GOBJECT_IO, in which case the callback will be
        invoked from an async IO handler.
      - EVENT_LOOP_WAIT, in which case the caller must invoke wait() to
        handle incoming messages.
    @param name: An optional name for the client
    '''
    self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    self.callbacks = set()
    self.event_loop = event_loop
    logging.debug('Initializing event client')

    should_start_thread = event_loop not in (
        self.EVENT_LOOP_GOBJECT_IO, self.EVENT_LOOP_WAIT)

    path = path or os.environ[CROS_FACTORY_EVENT]
    self.socket.connect(path)

    hello = self.socket.recv(len(_HELLO_MESSAGE))
    if hello != _HELLO_MESSAGE:
      raise socket.error('Event client expected hello (%r) but got %r' %
                         _HELLO_MESSAGE, hello)

    self._lock = threading.Lock()

    if callback:
      if isinstance(event_loop, Queue):
        self.callbacks.add(
          lambda event: event_loop.put(
            lambda: callback(event)))
      elif event_loop == self.EVENT_LOOP_GOBJECT_IDLE:
        import gobject
        self.callbacks.add(
          lambda event: gobject.idle_add(callback, event))
      elif event_loop == self.EVENT_LOOP_GOBJECT_IO:
        import gobject
        gobject.io_add_watch(
          self.socket, gobject.IO_IN,
          lambda source, condition: self._read_one_message()[0])
        self.callbacks.add(callback)
      else:
        self.callbacks.add(callback)

    if should_start_thread:
      self.recv_thread = threading.Thread(
        target=self._run_recv_thread,
        name='EventServerRecvThread-%s' % (name or get_unique_id()))
      self.recv_thread.daemon = True
      self.recv_thread.start()
    else:
      self.recv_thread = None

  def close(self):
    '''Closes the client, waiting for any threads to terminate.'''
    if not self.socket:
      return

    # Shutdown the socket to cause recv_thread to terminate.
    self.socket.shutdown(socket.SHUT_RDWR)
    if self.recv_thread:
      self.recv_thread.join()
    self.socket.close()
    self.socket = None

  def __del__(self):
    self.close()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    try:
      self.close()
    except:
      pass
    return False

  def _truncate_event_for_debug_log(self, event):
    '''
    Truncates event to a size of _MAX_EVENT_SIZE_FOR_DEBUG_LOG.

    Args:
      event: The event to be printed.

    Returns:
      Truncated event string representation.
    '''
    event_repr = repr(event)
    if len(event_repr) > _MAX_EVENT_SIZE_FOR_DEBUG_LOG:
      return event_repr[:_MAX_EVENT_SIZE_FOR_DEBUG_LOG] + '...'
    else:
      return event_repr

  def post_event(self, event):
    '''
    Posts an event to the server.
    '''
    if logging.getLogger().isEnabledFor(logging.DEBUG):
      logging.debug('Event client: sending event %s',
                    self._truncate_event_for_debug_log(event))
    message = pickle.dumps(event, protocol=2)
    if len(message) > _MAX_MESSAGE_SIZE:
      # Log it first so we know what event caused the problem.
      logging.error("Message too large (%d bytes): event is %s" %
             (len(message), event))
      raise IOError("Message too large (%d bytes)" % len(message))
    self.socket.sendall(message)

  def wait(self, condition, timeout=None):
    '''
    Waits for an event matching a condition.

    Args:
      condition: A function to evaluate. The function takes one
        argument (an event to evaluate) and returns whether the condition
        applies.
      timeout: A timeout in seconds. wait will return None on
        timeout.

    Returns:
      The event that matched the condition, or None if the connection
      was closed.
    '''
    if self.event_loop == self.EVENT_LOOP_WAIT:
      assert not timeout, 'Timeout is not currently supported in wait()'

      # We are the event loop.
      while True:
        keep_going, event = self._read_one_message()
        if not keep_going:  # Closed
          return None
        if event and condition(event):
          return event

    queue = Queue()

    def check_condition(event):
      if condition(event):
        queue.put(event)

    try:
      with self._lock:
        self.callbacks.add(check_condition)
      return queue.get(timeout=timeout)
    except Empty:
      return None
    finally:
      with self._lock:
        self.callbacks.remove(check_condition)

  def _run_recv_thread(self):
    '''
    Thread to receive messages and broadcast them to callbacks.
    '''
    while self._read_one_message()[0]:
      pass

  def _read_one_message(self):
    '''
    Handles one incoming message from the socket.

    Returns:
      (keep_going, event), where:
        keep_going: True if event processing should continue (i.e., not EOF).
        event: The message if any.
    '''
    bytes = self.socket.recv(_MAX_MESSAGE_SIZE + 1)
    if len(bytes) > _MAX_MESSAGE_SIZE:
      # The message may have been truncated - ignore it
      logging.error('Event client: message too large')
      return True, None

    if len(bytes) == 0:
      return False, None

    try:
      event = pickle.loads(bytes)
      if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug('Event client: dispatching event %s',
                      self._truncate_event_for_debug_log(event))
    except:
      logging.warn('Event client: bad message %r', bytes)
      traceback.print_exc(sys.stderr)
      return True, None

    with self._lock:
      callbacks = list(self.callbacks)
    for callback in callbacks:
      try:
        callback(event)
      except:
        logging.warn('Event client: error in callback')
        traceback.print_exc(sys.stderr)
        # Keep going

    return True, event
