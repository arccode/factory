#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input log file plugin.

Repeatedly reads lines from a log file.  Truncates the file when the maximum
size has been reached.

Default implementation assumes log file contains lines of JSON.  Can be
subclassed with different implementation of ParseLine.
"""

from __future__ import print_function

import contextlib
import json
import os
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils


_DEFAULT_POLL_INTERVAL = 1
_DEFAULT_MAX_BYTES = 4 * 1024 * 1024  # 4mb


class InputLogFile(plugin_base.InputPlugin):

  ARGS = [
      Arg('path', (str, unicode), 'Path to the log file on disk.',
          optional=False),
      Arg('poll_interval', (int, float),
          'Interval in seconds when the log file is checked for updates.',
          optional=True, default=_DEFAULT_POLL_INTERVAL),
      Arg('max_bytes', int,
          'Maximum size of the log file in bytes before being truncated.  '
          'Defaults to 4 MB.  '
          'If set to None, truncating functionality will be disabled.',
          optional=True, default=_DEFAULT_MAX_BYTES)
  ]

  def Main(self):
    """Main thread of the plugin."""
    last_size = self.ReadOffset()
    self.info('Starting offset for %s at %d', self.args.path, last_size)
    while not self.IsStopping():
      size = os.path.getsize(self.args.path)
      if size > last_size:
        self.info('%s size grew from %d to %d',
                     self.args.path, last_size, size)
        try:
          with file_utils.FileLock(self.args.path):
            if self.ParseAndEmit(self.args.path, offset=last_size):
              if size > self.args.max_bytes:
                self.info('Truncating %s to 0 bytes', self.args.path)
                with open(self.args.path, 'w'):
                  pass
                last_size = 0
              else:
                last_size = size
              self.WriteOffset(last_size)
            else:
              self.error('Emit failed')
        except IOError:
          self.error('Could not acquire file lock on %s', self.args.path)
      elif size < last_size:
        self.info('%s unexpectedly shrunk, resetting from %d to 0',
                     self.args.path, last_size)
        last_size = 0
      time.sleep(self.args.poll_interval)

  def ParseAndEmit(self, path, offset=0):
    """Parses lines starting at the given offset, and emits to Instalog."""
    events = []
    for line in self.Readlines(path, offset):
      try:
        events.append(self.ParseLine(line.rstrip()))
      except Exception as e:
        self.error('Parsing line "%s" failed, silently ingoring: %s', line, e)
    return self.Emit(events)

  def Readlines(self, path, offset=0):
    """Generates stripped lines from the file starting at the given offset."""
    with open(path, 'r') as f:
      f.seek(offset)
      for line in f:
        self.debug('Reading line: %s', line.rstrip())
        yield line

  def ParseLine(self, line):
    """Parses the given line into an Instalog Event object.

    Should be overridden in a subclass if necessary.

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
