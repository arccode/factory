# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import abc
import errno
import json
import logging
import os
import pickle
import queue
import select
import socket
import socketserver
import sys
import tempfile
import threading
import time
import traceback

from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


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
_HELLO_MESSAGE = b'\1'


def json_default_repr(obj):
  """Converts an object into a suitable representation for
  JSON-ification.

  If obj is an object, this returns a dict with all properties
  not beginning in '_'. Otherwise, the original object is
  returned.
  """
  if isinstance(obj, object):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
  return obj


class Event:
  """An event object that may be written to the event server.

  E.g.:

    event = Event(Event.Type.STATE_CHANGE,
                  test='foo.bar',
                  state=TestState(...))
  """
  class Type:
    # The state of a test has changed.
    STATE_CHANGE = 'goofy:state_change'
    # The UI has come up.
    UI_READY = 'goofy:ui_ready'
    # Tells goofy to clear all state and restart testing.
    RESTART_TESTS = 'goofy:restart_tests'
    # Tells goofy to run all tests that haven't been run yet.
    AUTO_RUN = 'goofy:auto_run'
    # Tells goofy to set all failed tests' state to untested and re-run.
    RUN_TESTS_WITH_STATUS = 'goofy:run_tests_with_status'
    # Clears state of all tests underneath the given path.
    CLEAR_STATE = 'goofy:clear_state'
    # Tells the UI about a single new line in the log.
    LOG = 'goofy:log'
    # A hello message to a new WebSocket. Contains a 'uuid' parameter
    # identification the particular invocation of the server.
    HELLO = 'goofy:hello'
    # A keepalive message from the UI. Contains a 'uuid' parameter
    # containing the same 'uuid' value received when the client received
    # its HELLO.
    KEEPALIVE = 'goofy:keepalive'
    # Initializes the test UI.
    INIT_TEST_UI = 'goofy:init_test_ui'
    # Sets layout for the test UI.
    SET_TEST_UI_LAYOUT = 'goofy:set_test_ui_layout'
    # Sets the UI in the test pane.
    SET_HTML = 'goofy:set_html'
    # Import a HTML fragment to test pane.
    IMPORT_HTML = 'goofy:import_html'
    # Runs JavaScript in the test pane.
    RUN_JS = 'goofy:run_js'
    # Performs a remote procedure call to the Chrome extension inside UI.
    EXTENSION_RPC = 'goofy:extension_rpc'
    # Event from a test UI.
    TEST_UI_EVENT = 'goofy:test_ui_event'
    # Message from test UI to new event loop to end the event loop.
    END_EVENT_LOOP = 'goofy:end_event_loop'
    # Message to tell the test UI to destroy itself.
    DESTROY_TEST = 'goofy:destroy_test'
    # Message telling Goofy should re-read system info.
    UPDATE_SYSTEM_INFO = 'goofy:update_system_info'
    # Tells Goofy to stop all tests.
    STOP = 'goofy:stop'
    # Indicates a pending shutdown.
    PENDING_SHUTDOWN = 'goofy:pending_shutdown'
    # Cancels a pending shutdown.
    CANCEL_SHUTDOWN = 'goofy:cancel_shutdown'
    # Tells UI to update notes.
    UPDATE_NOTES = 'goofy:update_notes'
    # Diagnosis Tool's events
    DIAGNOSIS_TOOL_EVENT = 'goofy:diagnosis_tool:event'
    # Notifies that factory server config (URL, timeout) is changed.
    FACTORY_SERVER_CONFIG_CHANGED = 'factory_server:config_changed'
    # Notifies that the iterations or retries of a factory test is changed.
    SET_ITERATIONS_AND_RETRIES = 'goofy:set_iterations_and_retries'

  def __init__(self, type, **kw):  # pylint: disable=redefined-builtin
    self.type = type
    self.timestamp = time.time()
    for k, v in kw.items():
      setattr(self, k, v)

  def __repr__(self):
    return type_utils.StdRepr(
        self,
        extra=[
            'type=%s' % self.type,
            'timestamp=%s' % time.ctime(self.timestamp)],
        excluded_keys=['type', 'timestamp'])

  def to_json(self):
    return json.dumps(self, default=json_default_repr)

  @staticmethod
  def from_json(encoded_event):
    kw = json.loads(encoded_event)
    type = kw.pop('type')  # pylint: disable=redefined-builtin
    return Event(type=type, **kw)

  def __eq__(self, other):
    return (isinstance(other, Event) and
            json_default_repr(self) == json_default_repr(other))

  def __ne__(self, other):
    return not self == other

_unique_id_lock = threading.Lock()
_unique_id = 1


def get_unique_id():
  global _unique_id  # pylint: disable=global-statement
  with _unique_id_lock:
    ret = _unique_id
    _unique_id += 1
  return ret


class EventServerRequestHandler(socketserver.BaseRequestHandler):
  """Request handler for the event server.

  This class is agnostic to message format (except for logging).
  """

  def setup(self):
    socketserver.BaseRequestHandler.setup(self)
    threading.current_thread().name = (
        'EventServerRequestHandler-%d' % get_unique_id())
    # A thread to be used to send messages that are posted to the queue.
    self.send_thread = None
    # A queue containing messages.
    self.queue = queue.Queue()

  def handle(self):
    # The handle() methods is run in a separate thread per client
    # (since EventServer has ThreadingMixIn).
    logging.debug('Event server: handling new client')
    try:
      self.server._subscribe(self.queue)  # pylint: disable=protected-access

      # Send hello, now that we've subscribed.  Client will wait for
      # it before returning from the constructor.
      self.request.send(_HELLO_MESSAGE)

      self.send_thread = process_utils.StartDaemonThread(
          target=self._run_send_thread,
          name='EventServerSendThread-%d' % get_unique_id())

      # Process events: continuously read message and broadcast to all
      # clients' queues.
      while True:
        msg = self.request.recv(_MAX_MESSAGE_SIZE + 1)
        if len(msg) > _MAX_MESSAGE_SIZE:
          logging.error('Event server: message too large')
        if not msg:
          break  # EOF
        self.server._post_message(msg)  # pylint: disable=protected-access
    except socket.error as e:
      if e.errno in [errno.ECONNRESET, errno.ESHUTDOWN, errno.EPIPE]:
        pass  # Client just quit
      else:
        raise
    finally:
      logging.debug('Event server: client disconnected')
      self.queue.put(None)  # End of stream; make writer quit
      self.server._unsubscribe(self.queue)  # pylint: disable=protected-access

  def _run_send_thread(self):
    while True:
      message = self.queue.get()
      if message is None:
        return
      try:
        self.request.send(message)
      except Exception:
        return


class EventServer(socketserver.ThreadingUnixStreamServer):
  """An event server that broadcasts messages to all clients.

  This class is agnostic to message format (except for logging).
  """
  allow_reuse_address = True
  socket_type = socket.SOCK_SEQPACKET
  daemon_threads = True

  def __init__(self, path=None):
    """Constructor.

    Args:
      path: Path at which to create a UNIX stream socket.
          If None, uses a temporary path and sets the CROS_FACTORY_EVENT
          environment variable for future clients to use.
    """
    # pylint: disable=super-init-not-called
    # A set of queues listening to messages.
    self._queues = set()
    # A lock guarding the _queues variable.
    self._lock = threading.Lock()
    self._temp_path = None
    if not path:
      path = tempfile.mktemp(prefix='cros_factory_event.')
      os.environ[CROS_FACTORY_EVENT] = path
      logging.info('Setting %s=%s', CROS_FACTORY_EVENT, path)
      self._temp_path = path
    # pylint: disable=non-parent-init-called
    socketserver.UnixStreamServer.__init__(
        self, path, EventServerRequestHandler)

  def server_close(self):
    """Cleanup temporary file"""
    socketserver.ThreadingUnixStreamServer.server_close(self)
    if self._temp_path is not None:
      file_utils.TryUnlink(self._temp_path)

  def _subscribe(self, q):
    """Subscribes a queue to receive events.

    Invoked only from the request handler.
    """
    with self._lock:
      self._queues.add(q)

  def _unsubscribe(self, q):
    """Unsubscribes a queue to receive events.

    Invoked only from the request handler.
    """
    with self._lock:
      self._queues.discard(q)

  def _post_message(self, message):
    """Posts a message to all clients.

    Invoked only from the request handler.
    """
    try:
      if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug('Event server: dispatching object %s',
                      pickle.loads(message))
    except Exception:
      # Message isn't parseable as a pickled object; weird!
      logging.info(
          'Event server: dispatching message %r', message)

    with self._lock:
      for q in self._queues:
        # Note that this is nonblocking (even if one of the
        # clients is dead).
        q.put(message)


class EventClientBase(metaclass=abc.ABCMeta):
  """A client used to post and receive messages from an event server.

  All events sent through this class must be subclasses of Event. It
  marshals Event classes through the server by pickling them.

  The _process_event() need to be called periodically.

  Inherit graph:
  EventClientBase:
    |-- ThreadingEventClient: A daemon thread to process events.
    |-- BlockingEventClient: A while-loop on calling thread to process events.
  """
  def __init__(self, path=None, callback=None):
    """Constructor.

    Args:
      path: The UNIX seqpacket socket endpoint path. If None, uses
          the CROS_FACTORY_EVENT environment variable.
      callback: A callback to call when events occur. The callback
          takes one argument: the received event.
    """
    self.socket = self._ConnectSocket(path)

    self.callbacks = set()
    logging.debug('Initializing event client')

    if callback:
      self.callbacks.add(callback)

    self._lock = threading.Lock()

  def close(self):
    """Closes the client."""
    if self.socket:
      self.socket.shutdown(socket.SHUT_RDWR)
      self.socket.close()
      self.socket = None

  def is_closed(self):
    """Return whether the client is closed."""
    return self.socket is None

  def _ConnectSocket(self, path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    path = path or os.environ[CROS_FACTORY_EVENT]
    s.connect(path)

    hello = s.recv(len(_HELLO_MESSAGE))
    if hello != _HELLO_MESSAGE:
      raise socket.error('Event client expected hello (%r) but got %r' %
                         _HELLO_MESSAGE, hello)
    return s

  def __del__(self):
    self.close()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    # pylint: disable=redefined-outer-name
    del exc_type, exc_value, traceback  # Unused.
    try:
      self.close()
    except Exception:
      pass
    return False

  def _truncate_event_for_debug_log(self, event):
    """Truncates event to a size of _MAX_EVENT_SIZE_FOR_DEBUG_LOG.

    Args:
      event: The event to be printed.

    Returns:
      Truncated event string representation.
    """
    event_repr = repr(event)
    if len(event_repr) > _MAX_EVENT_SIZE_FOR_DEBUG_LOG:
      return event_repr[:_MAX_EVENT_SIZE_FOR_DEBUG_LOG] + '...'
    return event_repr

  def post_event(self, event):
    """Posts an event to the server."""
    if logging.getLogger().isEnabledFor(logging.DEBUG):
      logging.debug('Event client: sending event %s',
                    self._truncate_event_for_debug_log(event))
    message = pickle.dumps(event)
    if len(message) > _MAX_MESSAGE_SIZE:
      # pylint: disable=logging-too-many-args
      logging.error(b'Message too large (%d bytes): event type = %s, '
                    b'truncated message: %s', len(message), event.type,
                    message[:_MAX_MESSAGE_SIZE // 20] +
                    b'\n\n...SKIPED...\n\n' +
                    message[-_MAX_MESSAGE_SIZE // 20:])
      raise IOError('Message too large (%d bytes)' % len(message))
    self.socket.sendall(message)

  def _process_event(self, timeout=None):
    """Handles one incoming message from the socket.

    Throws:
      socket.timeout: If no event is received within timeout.

    Returns:
      (keep_going, event), where:
        keep_going: True if event processing should continue (i.e., not EOF).
        event: The message if any.
    """
    if timeout is not None:
      rlist, unused_wlist, unused_xlist = select.select([self.socket], [], [],
                                                        timeout)
      if self.socket not in rlist:
        raise socket.timeout
    msg_bytes = self.socket.recv(_MAX_MESSAGE_SIZE + 1)
    if len(msg_bytes) > _MAX_MESSAGE_SIZE:
      # The message may have been truncated - ignore it
      logging.error('Event client: message too large')
      return True, None

    if not msg_bytes:
      return False, None

    try:
      event = pickle.loads(msg_bytes)
      if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug('Event client: dispatching event %s',
                      self._truncate_event_for_debug_log(event))
    except Exception:
      logging.warning('Event client: bad message %r', msg_bytes)
      traceback.print_exc(sys.stderr)
      return True, None

    with self._lock:
      callbacks = list(self.callbacks)
    for callback in callbacks:
      try:
        callback(event)
      except Exception:
        logging.warning('Event client: error in callback')
        traceback.print_exc(sys.stderr)
        # Keep going

    return True, event

  @abc.abstractmethod
  def request_response(self, request_event, check_response, timeout=None):
    """Starts a request-response communication: sends a request event and waits
    for an valid response event until timeout.

    Args:
      request_event: An event to start protocol. None to send no events.
      check_response: A function to evaluate if given event is an expected
          response. The function takes one argument (an event to evaluate) and
          returns whether it is valid. Note it may also get events "before"
          request_event is sent, including the request_event itself.
      timeout: A timeout in seconds, or None to wait forever.

    Returns:
      The valid response event, or None if the connection was closed or timeout.
    """
    raise NotImplementedError

  def wait(self, condition, timeout=None):
    """Waits for an event matching a condition.

    Args:
      condition: A function to evaluate. The function takes one
          argument (an event to evaluate) and returns whether the condition
          applies.
      timeout: A timeout in seconds, or None to wait forever.

    Returns:
      The event that matched the condition, or None if the connection
      was closed or timeout.
    """
    return self.request_response(None, condition, timeout)


class BlockingEventClient(EventClientBase):
  """A blocking event client.

  A while-loop is used to serve as the event loop. This will block the
  calling thread, until the specified condition is met.

  Note that, the event loop only runs in request_response() and wait() calls,
  so the callbacks will be called only when these calls are invoked.
  """
  def request_response(self, request_event, check_response, timeout=None):
    """See EventClientBase.request_response."""

    start = None
    if timeout is not None:
      start = time_utils.MonotonicTime()

    if request_event:
      self.post_event(request_event)

    while True:
      next_timeout = None
      if timeout is not None:
        elapsed = time_utils.MonotonicTime() - start
        next_timeout = timeout - elapsed
        if next_timeout <= 0.0:
          return None  # timed out since specified event is not received

      try:
        keep_going, event = self._process_event(timeout=next_timeout)
      except socket.timeout:
        return None  # timed out since no event received

      if not keep_going:  # Closed
        return None

      if event and check_response(event):
        return event


class ThreadingEventClient(EventClientBase):
  """A threaded event client.

  A daemon thread is created in constructor to process events. After instance is
  constructed, callbacks will be called from that thread with incoming events.
  """
  def __init__(self, path=None, callback=None, name=None):
    """Constructor.

    Args:
      path: See EventClientBase.__init__.
      callback: See EventClientBase.__init__.
      name: An optional name for the receving thread.
    """
    super(ThreadingEventClient, self).__init__(path, callback)

    self.recv_thread = process_utils.StartDaemonThread(
        target=self._run_recv_thread,
        name='EventServerRecvThread-%s' % (name or get_unique_id()))

  def close(self):
    super(ThreadingEventClient, self).close()
    if self.recv_thread:
      self.recv_thread.join()
      self.recv_thread = None

  def _run_recv_thread(self):
    """Thread to receive messages and broadcast them to callbacks."""
    while self._process_event()[0]:
      pass

  def request_response(self, request_event, check_response, timeout=None):
    """See EventClientBase.request_response."""
    q = queue.Queue()

    def check_response_callback(event):
      if check_response(event):
        q.put(event)

    try:
      with self._lock:
        self.callbacks.add(check_response_callback)
        if request_event:
          self.post_event(request_event)
      return q.get(timeout=timeout)
    except queue.Empty:
      return None
    finally:
      with self._lock:
        self.callbacks.remove(check_response_callback)


def PostEvent(event):
  """Post the specified event to the server."""
  # Use a BlockingEventClient is sufficient, since we don't need to call the
  # callbacks from another thread.
  with BlockingEventClient() as event_client:
    # This will not blocked, since it's just a 'post' operation.
    event_client.post_event(event)


def PostNewEvent(event_type, *args, **kwargs):
  """Constructs an event from given type and parameters, and post it."""
  return PostEvent(Event(event_type, *args, **kwargs))


def SendEvent(request_event, check_response, timeout=None):
  """Send request_event to the server, and wait for a response until timeout.

  Args:
    request_event: An event to start protocol. None to send no events.
    check_response: A function to evaluate if given event is an expected
        response. The function takes one argument (an event to evaluate) and
        returns whether it is valid. Note it may also get events "before"
        request_event is sent, including the request_event itself.
    timeout: A timeout in seconds, or None to wait forever.

  Returns:
    The valid response event, or None if the connection was closed or timeout.
  """
  with BlockingEventClient() as event_client:
    return event_client.request_response(request_event, check_response, timeout)
