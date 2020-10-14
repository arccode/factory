# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A collection of mock classes for plugin unittests."""

# TODO(kitching): Add locks to ensure multi-threading support.

import copy
import logging
import os
import shutil
import tempfile

from cros.factory.instalog import plugin_base
from cros.factory.instalog import plugin_sandbox
from cros.factory.instalog.utils import file_utils


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
    self._att_dir = tempfile.mkdtemp(prefix='instalog_testing_')
    self.emit_calls = []
    self.streams = []

  def Close(self):
    """Performs any final operations."""
    shutil.rmtree(self._att_dir)

  def AllStreamsExpired(self):
    """Returns True if all streams are currently expired."""
    return all([stream.expired for stream in self.streams])

  def Emit(self, plugin, events):
    """Stores the events from this Emit call into self.emit_calls."""
    del plugin
    for event in events:
      # Move attachments to a temporary directory to simulate buffer.
      for att_id, att_path in event.attachments.items():
        # Use a filename that contains the original one for clarity.
        tmp_path = file_utils.CreateTemporaryFile(
            prefix=os.path.basename(att_path) + '_', dir=self._att_dir)
        # Relocate the attachment and update the event path.
        logging.debug('Moving attachment %s --> %s...', att_path, tmp_path)
        shutil.move(att_path, tmp_path)
        event.attachments[att_id] = tmp_path
    self.emit_calls.append(events)
    return True

  def GetStream(self, stream_id):
    """Retrieves the stream with the given ID, creating if necessary."""
    assert 0 <= stream_id <= len(self.streams)
    if stream_id < len(self.streams):
      return self.streams[stream_id]
    stream = MockBufferEventStream()
    self.streams.append(stream)
    return stream

  def NewStream(self, plugin):
    """Returns the next available EventStream (with Events in it)."""
    del plugin
    ret_stream = None
    # First, look for an expired stream with events in it.
    for stream in self.streams:
      if stream.expired and not stream.Empty():
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

  def GetProgress(self, plugin):
    """Returns the progress of the plugin through available events.

    Normally returns a tuple (completed_count, total_count), but for testing we
    don't require such a fine granularity of information.  Thus, we will simply
    return (0, 1) for incomplete, and (1, 1) for complete.  Completion is
    defined by all streams being empty.
    """
    del plugin
    for stream in self.streams:
      if not stream.Empty():
        return 0, 1
    return 1, 1

  def GetNodeID(self):
    """Returns a fake node ID."""
    return 'testing'


class MockBufferEventStream(plugin_base.BufferEventStream):
  """Implements a mock BufferEventStream class."""

  def __init__(self):
    self.expired = True
    self.queue = []
    self.consumed = []

  def Queue(self, events):
    """Queues the supplied events."""
    logging.debug('%s: Pushing %d events...', self, len(events))
    self.queue.extend(events)

  def Empty(self):
    """Returns whether or not there are events in this EventStream."""
    return len(self.queue) == 0 and len(self.consumed) == 0

  def Next(self):
    """Pops the next available Event or returns None if not available."""
    if self.expired:
      raise plugin_base.EventStreamExpired
    if not self.queue:
      logging.debug('%s: Nothing to pop', self)
      return None
    ret = self.queue.pop(0)
    self.consumed.append(ret)
    logging.debug('%s: Popping next event...', self)
    return copy.deepcopy(ret)

  def Commit(self):
    """Marks the EventStream as committed and expired."""
    if self.expired:
      raise plugin_base.EventStreamExpired
    self.consumed = []
    self.expired = True

  def Abort(self):
    """Marks the EventStream as aborted and expired."""
    if self.expired:
      raise plugin_base.EventStreamExpired
    self.queue = self.consumed + self.queue
    self.consumed = []
    self.expired = True
