# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog datatypes.

Represents data that moves through Instalog (events, attachments) and ways of
iterating through it.
"""

import copy
import datetime
import filecmp
import logging
import time

from cros.factory.instalog import json_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils import time_utils


class ProcessStage(json_utils.Serializable):
  """Represents a processing stage in the Event's history."""

  BUFFER = 'BUFFER'
  EXTERNAL = 'EXTERNAL'

  # pylint: disable=redefined-outer-name
  def __init__(self, node_id, time, plugin_id, plugin_type, target):
    self.node_id = node_id
    self.time = time
    self.plugin_id = plugin_id
    self.plugin_type = plugin_type
    self.target = target

  def ToDict(self):
    """Returns the dictionary equivalent of the ProcessStage object."""
    return {
        'node_id': self.node_id,
        'time': self.time,
        'plugin_id': self.plugin_id,
        'plugin_type': self.plugin_type,
        'target': self.target,
    }

  @classmethod
  def FromDict(cls, dct):
    """Returns a ProcessStage object from its dictionary equivalent."""
    if isinstance(dct['time'], datetime.datetime):
      dct['time'] = time_utils.DatetimeToUnixtime(dct['time'])
    return cls(
        dct['node_id'], dct['time'], dct['plugin_id'],
        dct['plugin_type'], dct['target'])

  def __repr__(self):
    """Implements repr function for debugging."""
    return ('ProcessStage(node_id=%r, time=%r, plugin_id=%r, '
            'plugin_type=%r, target=%r)'
            % (self.node_id, self.time, self.plugin_id,
               self.plugin_type, self.target))


class Event(json_utils.Serializable):
  """Represents an Instalog event.

  Properties:
    payload: A dictionary representing Event data.  It can be accessed either
             through normal dictionary operators on the Event object itself
             (e.g. event['field']), or through the `payload` properly
             (e.g. event.payload[0]).
    attachments: Dictionary of attachments for this event.  Key is a string
                 identifying the file attachment; might match an ID within the
                 event payload itself.  Value is where the file can be located
                 on the filesystem.  Assumed to have read permissions.
    history: A list representing the processing history of this Event.  A list
             of ProcessStage objects.  The first ProcessStage object represents
             the InputPlugin from which the Event originates.
  """

  def __init__(self, payload, attachments=None, history=None):
    self.payload = payload
    self.attachments = {} if attachments is None else attachments
    self.history = [] if history is None else history
    if not isinstance(self.payload, dict):
      raise TypeError('Provided payload argument must be of type `dict`')
    if not isinstance(self.attachments, dict):
      raise TypeError('Provided attachments argument must be of type `dict`')
    if not isinstance(self.history, list):
      raise TypeError('Provided history argument must be of type `list`')

  def AppendStage(self, process_stage):
    """Records the next processing stage in this Event's history."""
    self.history.append(process_stage)

  @classmethod
  def Deserialize(cls, json_string):
    """Deserializes an Event object given as a JSON string."""
    if isinstance(json_string, bytes):
      json_string = json_string.decode('utf-8')
    obj = json_utils.decoder.decode(json_string)

    # json_string = '{"__type__": "Event", "payload": {payload}, '
    #               '"attachments": {attachments}, "history": {history}}'
    if isinstance(obj, Event):
      return obj
    # Legacy object serialization.
    # json_string = '[{payload}, {attachments}]'
    if isinstance(obj, list):
      if len(obj) != 2:
        raise ValueError('Given JSON string is a list, but the length is not 2')
      return cls(
          payload=obj[0],
          attachments=obj[1])
    # Case of only 'payload' being provided (run_plugin.py).
    # json_string = '{payload}'
    if isinstance(obj, dict):
      return cls(payload=obj)

    raise ValueError('Unable to deserialize the JSON string: %s' %
                     json_string)

  def ToDict(self):
    """Returns the dictionary equivalent of the Event object."""
    return {
        'payload': self.payload,
        'attachments': self.attachments,
        'history': self.history,
    }

  @classmethod
  def FromDict(cls, dct):
    """Returns an Event object from its dictionary equivalent."""
    return cls(
        payload=dct['payload'],
        attachments=dct['attachments'],
        history=dct['history'])

  def __repr__(self):
    """Implements repr function for debugging."""
    return ('Event(payload=%s, attachments=%s, history=%s)'
            % (self.payload, self.attachments, self.history))

  def __eq__(self, other):
    """Implements == operator."""
    if not self.payload == other.payload:
      return False
    if not len(self.attachments) == len(other.attachments):
      return False
    for att_id, att_path in self.attachments.items():
      if att_id not in other.attachments:
        return False
      other_path = other.attachments[att_id]
      if att_path != other_path and not filecmp.cmp(att_path, other_path):
        return False
    return True

  def __ne__(self, other):
    """Implements != operator."""
    return not self == other

  def __getitem__(self, key):
    """Implements dict [] get operator."""
    return self.payload[key]

  def get(self, key, default=None):
    """Implements dict get function."""
    return self.payload.get(key, default)

  def __setitem__(self, key, value):
    """Implements dict [] set operator."""
    self.payload[key] = value

  def __contains__(self, item):
    """Implements dict `in` operator."""
    return item in self.payload

  def keys(self):
    """Implements dict keys function."""
    return list(self.payload)

  def values(self):
    """Implements dict values function."""
    return list(self.payload.values())

  def iteritems(self):
    """Implements iteritems function."""
    return iter(self.payload.items())

  def setdefault(self, key, default):
    """Implements setdefault function."""
    return self.payload.setdefault(key, default)

  def __copy__(self):
    """Implements __copy__ function."""
    return Event(self.payload, self.attachments, self.history)

  def __deepcopy__(self, memo):
    """Implements __deepcopy__ function."""
    result = self.__class__(copy.deepcopy(self.payload),
                            copy.deepcopy(self.attachments),
                            copy.deepcopy(self.history))
    # Avoid excess copying if the Event is referenced from within the Event.
    memo[id(self)] = result
    return result

  def Copy(self):
    """Uses __copy__ to return a shallow copy of this Event."""
    return self.__copy__()


class EventStream:
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

  def Next(self, timeout=1):
    """Gets the next available event from the buffer.

    Just like a normal Python iterable, should raise StopIteration when no
    more events are available.  However, in the case that the plugin has been
    paused, a WaitException will be raised.

    Args:
      timeout: Seconds to wait for retrieving next event.

    Returns:
      None if timeout or no more events are currently available.

    Raises:
      WaitException if the plugin has been paused.
    """
    ret = self._plugin_api.EventStreamNext(self._plugin, self, timeout)
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


class EventStreamIterator:
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
  _DEFAULT_INTERVAL = 0.5

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
    self._start = time_utils.MonotonicTime()

  def __iter__(self):
    """Returns self for special __iter__ function."""
    return self

  def __next__(self):
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
      if (self.blocking and
          (time_utils.MonotonicTime() - self._start) >= self.timeout):
        logging.debug('Iterator timeout!')
        raise StopIteration

      # Try getting the next event.  If the plugin is in a waiting state,
      # stop iteration immediately.
      try:
        remaining_time = self._start + self.timeout - time_utils.MonotonicTime()
        ret = self.event_stream.Next(timeout=remaining_time)
      except plugin_base.WaitException:
        raise StopIteration

      # We have a value, exit the loop.
      if ret is not None:
        break

      # If the current plugin is flushing, we should raise StopIteration
      # regardless of whether self.blocking is set.
      # TODO(chuntsen): fix pylint error
      # pylint: disable=protected-access
      if self.event_stream._plugin_api.IsFlushing(self.event_stream._plugin):
        logging.debug('Flushing!')
        raise StopIteration

      # No new events available, take appropriate action.
      if self.blocking:
        # If the remaining time is less than the interval, stop iteration
        # immediately.
        if (self.timeout - (time_utils.MonotonicTime() - self._start) <=
            self.interval):
          raise StopIteration
        time.sleep(self.interval)
        continue
      raise StopIteration

    self._current_count += 1
    return ret
