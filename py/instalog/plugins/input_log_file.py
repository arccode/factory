#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input log file plugin.

Repeatedly reads lines from a log file.  Truncates the file when the maximum
size has been reached.  This plugin is only guaranteed not to result in any data
loss when the application writing into the log file locks the log file during
writes.  Otherwise, some data loss may occur between the call to getsize and the
truncate write.

Default implementation assumes log file contains lines of JSON.  Can be
subclassed with different implementation of ParseLine.
"""

from __future__ import print_function

import json
import os
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils


_DEFAULT_POLL_INTERVAL = 2
_DEFAULT_BATCH_SIZE = 500
_DEFAULT_BATCH_PAUSE_TIME = 0.1
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10mb


class InputLogFile(plugin_base.InputPlugin):

  ARGS = [
      Arg('path', (str, unicode), 'Path to the log file on disk.',
          optional=False),
      Arg('poll_interval', (int, float),
          'Interval in seconds when the log file is checked for updates.',
          optional=True, default=_DEFAULT_POLL_INTERVAL),
      Arg('batch_pause_time', (int, float),
          'Time in seconds to wait when a batch has completed processing, but '
          'more data still remains.',
          optional=True, default=_DEFAULT_BATCH_PAUSE_TIME),
      Arg('batch_size', int,
          'Maximum number of events to emit at a time.',
          optional=True, default=_DEFAULT_BATCH_SIZE),
      Arg('max_bytes', int,
          'Maximum size of the log file in bytes before being truncated.  '
          'Defaults to 4 MB.  '
          'If set to 0, truncating functionality will be disabled.',
          optional=True, default=_DEFAULT_MAX_BYTES)
  ]

  # Stores the last offset written to disk.
  last_written_offset = None

  def Main(self):
    """Main thread of the plugin."""
    last_offset = self.ReadOffset()
    self.info('Starting offset for %s at %d', self.args.path, last_offset)
    while not self.IsStopping():
      try:
        size = os.path.getsize(self.args.path)
      except OSError:
        # Maybe the file doesn't currently exist, or we don't have access.
        # Reset the offset to zero.
        if last_offset != 0:
          self.info('Input file %s not found, set offset to 0', self.args.path)
          last_offset = 0
          self.WriteOffset(last_offset)
        time.sleep(self.args.poll_interval)
        continue

      # If the following conditions hold true:
      #   (1) File truncating is enabled (max_bytes is not 0)
      #   (2) We have read all of the pending new events from the file
      #   (3) The current size is greater than the maximum allowed file size
      # Then attempt truncating the log file.
      if (self.args.max_bytes > 0 and
          last_offset == size and
          size > self.args.max_bytes):
        self.info('Input file %s size %d > max size %d, attempt truncate',
                  self.args.path, size, self.args.max_bytes)
        try:
          with file_utils.FileLock(self.args.path):
            # Make sure the size of the file hasn't grown since our last getsize
            # call outside of the FileLock.
            size = os.path.getsize(self.args.path)
            if last_offset == size:
              with open(self.args.path, 'w'):
                pass
          if last_offset < size:
            self.info('File %s already grew to %d bytes, abandon truncate',
                      self.args.path, size)
            time.sleep(self.args.poll_interval)
            continue
        except IOError:
          self.error('Could not acquire file lock on %s, abandon truncate',
                     self.args.path)
          time.sleep(self.args.poll_interval)
          continue
        else:
          self.info('Truncate successful')
          last_offset = 0
          self.WriteOffset(last_offset)
          time.sleep(self.args.poll_interval)
          continue

      if size > last_offset:
        self.info('%s progress: %d / %d',
                     self.args.path, last_offset, size)
        new_offset, emit_result = self.ParseAndEmit(
            self.args.path, offset=last_offset)
        self.debug('new_offset=%s, emit_result=%s',
                   new_offset, emit_result)
        if emit_result:
          last_offset = new_offset
          self.WriteOffset(last_offset)
          self.info('%s progress: %d / %d',
                       self.args.path, last_offset, size)
        else:
          self.error('Emit failed')
      elif size < last_offset:
        self.info('%s unexpectedly shrunk, resetting from %d to 0',
                     self.args.path, last_offset)
        last_offset = 0
        self.WriteOffset(last_offset)

      # If we still have more data to process right away, only pause for
      # batch_pause_time.  Otherwise, pause for poll_interval.
      time.sleep(self.args.batch_pause_time if last_offset < size
                 else self.args.poll_interval)

  def ParseAndEmit(self, path, offset=0):
    """Parses lines starting at the given offset, and emits to Instalog.

    Returns:
      A tuple, where the first element is the offset after processing the
      current batch of events, and the second element is the result from the
      Emit call (boolean representing its success).
    """
    events = []
    new_offset = offset
    num_lines = 0
    parse_fail_count = 0
    for new_offset, line in self.Readlines(path, offset):
      line = line.rstrip()
      try:
        events.append(self.ParseLine(line))
      except Exception as e:
        parse_fail_count += 1
        self.debug('Parsing line "%s" failed, silently ignoring: %s', line, e)

      # Count bogus lines as part of the "batch" -- otherwise, we might read a
      # huge file full of bogus without pausing.
      num_lines += 1
      if num_lines >= self.args.batch_size:
        break
    self.info('Parsed %d events, ignored %d bogus lines',
              len(events), parse_fail_count)
    return new_offset, self.Emit(events)

  def Readlines(self, path, offset=0):
    """Generates stripped lines from the file starting at the given offset.

    Returns:
      A tuple, where the first element is the offset after reading the current
      line, and the second element is the current line.
    """
    new_offset = offset
    with open(path, 'r') as f:
      f.seek(offset)
      for line in f:
        new_offset += len(line)
        self.debug('new_offset=%d, line=%r', new_offset, line.rstrip())
        yield new_offset, line

  def ParseLine(self, line):
    """Parses the given line into an Instalog Event object.

    Should be overridden in a subclass if necessary.

    Returns:
      A datatypes.Event object.

    Raises:
      Any exception if the line could not be correctly parsed.
    """
    data = json.loads(line)
    return datatypes.Event(data)

  def GetOffsetFile(self):
    """Returns the path to the offset file on disk."""
    return os.path.join(self.GetStateDir(), 'offset')

  def WriteOffset(self, offset):
    """Writes the current offset to disk."""
    if offset == self.last_written_offset:
      return
    self.last_written_offset = offset
    with file_utils.AtomicWrite(self.GetOffsetFile()) as f:
      f.write(str(offset))

  def ReadOffset(self):
    """Retrieves the current offset from disk.

    Returns:
      0 if the offset file does not exist.  Otherwise, the integer contained
      within the offset file.
    """
    if not os.path.exists(self.GetOffsetFile()):
      return 0
    with open(self.GetOffsetFile()) as f:
      return int(f.read())


if __name__ == '__main__':
  plugin_base.main()
