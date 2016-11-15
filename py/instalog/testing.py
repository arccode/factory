# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A collection of mock classes for plugin unittests."""

# TODO(kitching): Add locks to ensure multi-threading support.
# TODO(kitching): Add proper Abort support to MockBufferEventStream (events
#                 should be pushed back into Queue).

from __future__ import print_function

import logging
import Queue

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog import plugin_sandbox


class MockCore(plugin_sandbox.CoreAPI):
  """Implements CoreAPI as a mock object for testing.

  Allows low-level access to BufferEventStreams, as well as storing and playing
  back Emit call history.

  BufferEventStreams: Any number of BufferEventStreams can be created.  For
  example, if the plugin is single-threaded, one BufferEventStream is
  sufficient.  However, if you specifically want to separate Events into two
  batches that are separately read by the plugin as separate BufferEventStreams,
  you can create two BufferEventStream objects.  Usage: Use Queue to add Events
  to the MockBufferEventStream object returned by GetStream.  Example:

    mock_core.GetStream(0).Queue([datatypes.Event({})])

  Emit call history: Stored in the self.emit_calls instance variable as a list.
  The Event list from each call is appended to the emit_calls list every time
  Emit is called.  Example:

    self.assertEqual(mock_core.emit_calls[0], [datatypes.Event({})])
  """

  def __init__(self):
    self.emit_calls = []
    self.streams = []

  def Emit(self, plugin, events):
    """Stores the events from this Emit call into self.emit_calls."""
    del plugin
    self.emit_calls.append(events)

  def GetStream(self, stream_id):
    """Retrieves the stream with the given ID, creating if necessary."""
    assert stream_id >= 0 and stream_id <= len(self.streams)
    if stream_id < len(self.streams):
      return self.streams[stream_id]
    else:
      stream = MockBufferEventStream()
      self.streams.append(stream)
      return stream

  def NewStream(self, plugin):
    """Returns the next available EventStream (with Events in it)."""
    del plugin
    ret_stream = None
    # First, look for an expired stream with events in it.
    for stream in self.streams:
      if stream.expired and not stream.queue.empty():
        ret_stream = stream

    # Next, fall back to an expired stream without events.
    if not ret_stream:
      for stream in self.streams:
        if stream.expired:
          ret_stream = stream

    # Finally, if all streams are in use, create a new one.
    if not ret_stream:
      ret_stream = self.GetStream(len(self.streams))

    # Set to expired and return.
    ret_stream.expired = False
    logging.debug('NewStream returns: %s', ret_stream)
    return ret_stream


class MockBufferEventStream(plugin_base.BufferEventStream):
  """Implements a mock BufferEventStream class."""

  def __init__(self):
    self.expired = True
    self.queue = Queue.Queue()

  def Queue(self, events):
    """Queue the supplied events."""
    for event in events:
      logging.debug('%s: Pushing %s...', self, event)
      self.queue.put(event)

  def Next(self):
    """Pop the next available event or return None if not available."""
    if self.expired:
      raise plugin_base.EventStreamExpired
    if self.queue.empty():
      logging.debug('%s: Nothing to pop', self)
      return None
    ret = self.queue.get(False)
    logging.debug('%s: Popping %s...', self, ret)
    return ret

  def Commit(self):
    """Mark the EventStream as committed and expired."""
    if self.expired:
      raise plugin_base.EventStreamExpired
    self.expired = True

  def Abort(self):
    """Mark the EventStream as aborted and expired."""
    if self.expired:
      raise plugin_base.EventStreamExpired
    self.expired = True
