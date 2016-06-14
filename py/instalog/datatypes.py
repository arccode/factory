# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog datatypes.

Represents data that moves through Instalog (events, attachments) and ways of
iterating through it.
"""

from __future__ import print_function

import instalog_common  # pylint: disable=W0611


class Event(object):
  """Represents an Instalog event.

  Properties:
    attachments: Dictionary of attachments for this event.  Key is a string
                 identifying the file attachment; might match an ID within the
                 event data itself.  Value is where the file can be located on
                 the filesystem.  Assumed to have read permissions.
  """

  def __init__(self, data, attachments=None):
    self.attachments = attachments or {}
    self.data = data

  def __repr__(self):
    return str([self.data, self.attachments])


class EventStream(object):
  """Represents a stream of events for an output plugin to process."""

  def __init__(self, plugin, plugin_api):
    self._plugin = plugin
    self._plugin_api = plugin_api
    self._count = 0

  def Next(self):
    """Gets the next available event from the buffer.

    Just like a normal Python iterable, should raise StopIteration when no
    more events are available.  However, in the case that the plugin has been
    paused, a WaitException will be raised.

    Args:
      blocking: Whether or not it is a blocking call.  If non-blocking,
                the timeout argument has no effect, and any calls will return
                or raise an exception immediately.
      timeout: If no events are currently available, maximum number of seconds
               to block before raising StopIteration.  If set to 0 (default),
               will block indefinitely.

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
