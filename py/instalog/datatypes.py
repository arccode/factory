# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog datatypes.

Represents data that moves through Instalog (events, attachments) and ways of
iterating through it.
"""

from __future__ import print_function

import copy
import json
import logging
import time

import instalog_common  # pylint: disable=W0611
from instalog import json_utils
from instalog import plugin_base


class Event(object):
  """Represents an Instalog event.

  Properties:
    data: Event data.  If it is a dictionary, it can be accessed through normal
          dictionary operators on the event itself (e.g. event['field']).
          Otherwise, the `data` property can be directly accessed
          (e.g.  event.data[0]).
    attachments: Dictionary of attachments for this event.  Key is a string
                 identifying the file attachment; might match an ID within the
                 event data itself.  Value is where the file can be located on
                 the filesystem.  Assumed to have read permissions.
  """

  def __init__(self, data, attachments=None):
    self.data = data
    self.attachments = {} if attachments is None else attachments
    if not isinstance(self.attachments, dict):
      raise TypeError('Provided attachments argument must be of type `dict`')

  def Serialize(self):
    """Serialize an Event object."""
    return json.dumps([self.data, self.attachments], cls=json_utils.JSONEncoder)

  @classmethod
  def Deserialize(cls, json_string):
    """Deserialize an Event object.

    Args:
      json_string: JSON string of the event, as a two-element list:
                   json_string == [data, attachments].

    Returns:
      An Event object.
    """
    json_data = json.loads(json_string, cls=json_utils.JSONDecoder)
    data, attachments = json_data
    return cls(data, attachments)

  @classmethod
  def DeserializeRaw(cls, json_data=None, json_attachments=None):
    """Deserialize an Event object with data and attachments separated.

    TODO(kitching): Decide whether to allow both strings and dictionaries for
                    these two arguments.

    Provided for testing applications or use in CLI programs.

    Args:
      json_data: JSON string of the event data.
      json_attachments: JSON string of the attachments.

    Returns:
      An Event object.
    """
    data = (json.loads(json_data, cls=json_utils.JSONDecoder)
            if json_data is not None else {})
    attachments = (json.loads(json_attachments, cls=json_utils.JSONDecoder)
                   if json_attachments is not None else {})
    return cls(data, attachments)

  def __repr__(self):
    """Implements repr function for debugging."""
    return 'Event(%s, %s)' % (self.data, self.attachments)

  def __eq__(self, other):
    """Implements == operator."""
    return self.data == other.data and self.attachments == other.attachments

  def __ne__(self, other):
    """Implements != operator."""
    return not self == other

  def __getitem__(self, key):
    """Implements dict [] get operator."""
    return self.data[key]

  def get(self, key, default=None):
    """Implements dict get function."""
    # TODO(kitching): Test this method.
    return self.data.get(key, default)

  def __setitem__(self, key, value):
    """Implements dict [] set operator."""
    # TODO(kitching): Test this method.
    self.data[key] = value

  def __contains__(self, item):
    """Implements dict `in` operator."""
    return item in self.data

  def keys(self):
    """Implements dict keys function."""
    return self.data.keys()

  def values(self):
    """Implements dict values function."""
    return self.data.values()

  def iteritems(self):
    """Implements iteritems function."""
    return self.data.iteritems()

  def __copy__(self):
    """Implements __copy__ function."""
    return Event(self.data, self.attachments)

  def __deepcopy__(self, memo):
    """Implements __deepcopy__ function."""
    result = self.__class__(copy.deepcopy(self.data),
                            copy.deepcopy(self.attachments))
    # Avoid excess copying if the Event is referenced from within the Event.
    memo[id(self)] = result
    return result

  def Copy(self):
    """Uses __copy__ to return a shallow copy of this Event."""
    return self.__copy__()


class EventStream(object):
  """Represents a stream of events for an output plugin to process.

  Properties:
    _plugin: A reference to the plugin using this EventStream.
    _plugin_api: An instance of a class implementing PluginAPI.  Usually the
                 PluginSandbox of this plugin.
    _count: The number of events retrieved so far through this EventStream.
  """

  def __init__(self, plugin, plugin_api):
    self._plugin = plugin
    self._plugin_api = plugin_api
    self._count = 0

  def __iter__(self):
    return self.iter()

  def iter(self, *args, **kwargs):
    """Create an iterator to get events out of this EventStream.

    Refer to EventStreamIterator for argument specification.

    Returns:
      EventStreamIterator instance.
    """
    logging.debug('Creating a stream iterator...')
    return EventStreamIterator(self, *args, **kwargs)

  def GetCount(self):
    """The total number of events retrieved so far."""
    return self._count

  def Next(self):
    """Gets the next available event from the buffer.

    Just like a normal Python iterable, should raise StopIteration when no
    more events are available.  However, in the case that the plugin has been
    paused, a WaitException will be raised.

    Returns:
      None if no more events are currently available.

    Raises:
      WaitException if the plugin has been paused.
    """
    ret = self._plugin_api.EventStreamNext(self._plugin, self)
    if ret is not None:
      self._count += 1
      return ret

  def Commit(self):
    """Commits the current batch of events as successfully processed.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.EventStreamCommit(self._plugin, self)

  def Abort(self):
    """Aborts the current batch of events as failed to process.

    Raises:
      UnexpectedAccess if the plugin instance is in some unexpected state and
      is trying to access core functionality that it should not.
    """
    return self._plugin_api.EventStreamAbort(self._plugin, self)


class EventStreamIterator(object):
  """Iterator to get events out of an EventStream.

  Properties:
    event_stream: The EventStream from which to pull events.
    blocking: Whether or not to make a blocking call (wait when no events
              are available).
    timeout: If making a blocking call, the total time to wait for new events
             before timing out.  Timing starts when the iterator is created, and
             includes any time taken by the plugin to do work on the event.
    interval: Time to wait in between making next() calls.
    count: Number of events to retrieve before stopping.
    _current_count: Current number of events retrieved.
    _start: Start time, when this iterator was created.
  """

  # By default, whether or not to block on next() calls.
  _DEFAULT_BLOCKING = True

  # By default, how long to block on next() calls.  We want to prevent plugins
  # from accidentally blocking forever.
  _DEFAULT_TIMEOUT = 30

  # By default, how long to block in between failed next() call attempts.
  _DEFAULT_INTERVAL = 1

  # By default, how many events to pull until the iterator ends.  Default is
  # to pull events until no longer available.
  _DEFAULT_COUNT = float('inf')

  def __init__(self, event_stream, blocking=_DEFAULT_BLOCKING,
               timeout=_DEFAULT_TIMEOUT, interval=_DEFAULT_INTERVAL,
               count=_DEFAULT_COUNT):
    self.event_stream = event_stream
    self.blocking = blocking
    self.timeout = timeout
    self.interval = interval
    self.count = count
    self._current_count = 0
    self._start = time.time()

  def __iter__(self):
    """Returns self for special __iter__ function."""
    return self

  def next(self):
    """Returns next event from the EventStream.

    Raises:
      StopIteration if event count is reached, if timeout is reached,
      or if a WaitException is encountered.
    """
    while True:
      # Check to see if we have enough events.
      if self._current_count >= self.count:
        logging.debug('Count up!')
        raise StopIteration

      # Check to see if we have timed out.
      if self.blocking and (time.time() - self._start) >= self.timeout:
        logging.debug('Iterator timeout!')
        raise StopIteration

      # Try getting the next event.  If the plugin is in a waiting state,
      # stop iteration immediately.
      try:
        ret = self.event_stream.Next()
      except plugin_base.WaitException:
        raise StopIteration

      # We have a value, exit the loop.
      if ret is not None:
        break

      # No new events available, take appropriate action.
      if self.blocking:
        time.sleep(self.interval)
        continue
      else:
        raise StopIteration

    self._current_count += 1
    return ret
