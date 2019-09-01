#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import datetime
import itertools
import re
import sys

MAX_TIMESTAMP = datetime.datetime(datetime.MAXYEAR, 12, 31)

# Recognizable timestamp formats.
# A timestamp format is a tuple consists of:
#   1. Compiled regular expression pattern. Used to match the timestamp.
#   2. datetime format string. Used by datetime.strptime().
TIMESTAMP_PATTERN = [
    (re.compile(r'\d{4}-\d+-\d+T\d+:\d+:\d+\.\d+'),
     '%Y-%m-%dT%H:%M:%S.%f'),
    (re.compile(r'\d{4}-\d+-\d+ \d+:\d+:\d+\.\d+'),
     '%Y-%m-%d %H:%M:%S.%f')]


def ParseTimestamp(line):
  """Parse recognizable timestamp from log line.

  Tries to find a timestamp with format defined in TIMESTAMP_PATTERN.
  If found, parses the timestamp into datetime object.

  Returns:
    A datetime object if a timestamp is found. Otherwise, None.
  """
  for pattern, ptime in TIMESTAMP_PATTERN:
    match = pattern.search(line)
    if match is not None:
      return datetime.datetime.strptime(match.group(0), ptime)
  return None


class TimestampedFileReader(object):
  '''A reader that wraps file object.

  This reader buffers the next line read from the wrapped file object, and
  provides methods to query the timestamp within the line.

  When the line is read from the buffer, automatically reads and buffers the
  next line.
  '''

  def __init__(self, f):
    self._f = f
    self._time = datetime.datetime.utcfromtimestamp(0)
    self._next_line = None
    self._AdvanceLine()

  def __del__(self):
    self._f.close()

  def _AdvanceLine(self):
    self._next_line = self._f.readline()
    if self._next_line:
      self._time = ParseTimestamp(self._next_line) or self._time
    else:
      self._time = MAX_TIMESTAMP

  def GetTimestamp(self):
    return self._time

  def GetNextLine(self):
    ret = self._next_line
    self._AdvanceLine()
    return ret


EXAMPLES = """Examples:

  When analyzing logs captured by factory_bug:

    # Content of var/factory/log/factory.log
    [INFO] goofy goofy:1015 2012-11-15 01:00:15.293 Started
    [INFO] goofy goofy:290 2012-11-15 01:00:15.325 Starting state server
    [WARNING] goofy goofy:1030 2012-11-15 01:00:24.203 Dummy warning

    # Content of var/log/messages
    2012-11-15T01:00:17.668609+00:00 localhost kernel: [  243.193857] Foo.

    # Merge the two log files
    merge_logs var/factory/log/factory.log var/log/messages

    # Results
    0> [INFO] goofy goofy:1015 2012-11-15 01:00:15.293 Started
    0> [INFO] goofy goofy:290 2012-11-15 01:00:15.325 Starting state server
    1> 2012-11-15T01:00:17.668609+00:00 localhost kernel: [  243.193857] Foo.
    0> [WARNING] goofy goofy:1030 2012-11-15 01:00:24.203 Dummy warning

"""


def main():
  parser = argparse.ArgumentParser(
      description='Merge kernel/factory log by timestamps.',
      epilog=EXAMPLES,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('file', metavar='file', type=argparse.FileType('r'),
                      nargs='+', help='Log files to merge')
  parser.add_argument('-o', '--output', metavar='output_log',
                      type=argparse.FileType('w'), default=sys.stdout)
  args = parser.parse_args()
  reader = [TimestampedFileReader(f) for f in args.file]

  while True:
    ts, idx = min(itertools.izip([r.GetTimestamp() for r in reader],
                                 itertools.count()))
    if ts == MAX_TIMESTAMP:
      break
    args.output.write(str(idx) + '> ' + reader[idx].GetNextLine())

if __name__ == '__main__':
  main()
