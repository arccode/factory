#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input log file plugin.

Repeatedly reads lines from a set of log files.  Truncates each file when the
maximum size has been reached.  This plugin is only guaranteed not to result in
any data loss when the application writing into a log file locks the log file
during writes.  Otherwise, some data loss may occur between the call to
os.getsize and the truncate write operation.

Default implementation assumes log files contain lines of JSON.  Can be
subclassed with different implementation of either ParseEvents or ParseLine.
"""

import glob
import json
import logging
import os
import queue
import zlib

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import time_utils


_DEFAULT_NEW_FILE_POLL_INTERVAL = 60
_DEFAULT_POLL_INTERVAL = 2
_DEFAULT_ERROR_PAUSE_TIME = 60
_DEFAULT_BATCH_PAUSE_TIME = 0.1
_DEFAULT_BATCH_MAX_COUNT = 500
_DEFAULT_BATCH_MAX_BYTES = 1 * 1024 * 1024  # 1mb
_DEFAULT_MAX_BYTES = 0  # truncating disabled


class InputLogFile(plugin_base.InputPlugin):

  ARGS = [
      Arg('path', str,
          'Path to the set of log files on disk.  Uses glob syntax.'),
      Arg('new_file_poll_interval', (int, float),
          'Interval in seconds to check for new paths that match the glob.',
          default=_DEFAULT_NEW_FILE_POLL_INTERVAL),
      Arg('poll_interval', (int, float),
          'Interval in seconds when the log file is checked for updates.',
          default=_DEFAULT_POLL_INTERVAL),
      Arg('error_pause_time', (int, float),
          'Time in seconds to wait when an error occurs reading a file.',
          default=_DEFAULT_ERROR_PAUSE_TIME),
      Arg('batch_pause_time', (int, float),
          'Time in seconds to wait when a batch has completed processing, but '
          'more data still remains.',
          default=_DEFAULT_BATCH_PAUSE_TIME),
      Arg('batch_max_count', int,
          'Maximum number of events to emit at a time.',
          default=_DEFAULT_BATCH_MAX_COUNT),
      Arg('batch_max_bytes', int,
          'Maximum number of bytes to read from the log file at a time.',
          default=_DEFAULT_BATCH_MAX_BYTES),
      Arg('max_bytes', int,
          'Maximum size of the log file in bytes before being truncated.  '
          'If set to 0, truncating functionality will be disabled (default).',
          default=_DEFAULT_MAX_BYTES)
  ]

  def __init__(self, *args, **kwargs):
    self.log_files = {}
    super(InputLogFile, self).__init__(*args, **kwargs)

  def ScanLogFiles(self):
    """Updates the internal LogFile objects based on glob results.

    Returns:
      List of new LogFile objects.
    """
    new_log_files = []
    paths = glob.glob(self.args.path)
    for path in paths:
      if path not in self.log_files:
        # Since we replace os.sep with '_' in the offset filename, it is
        # possible for two different paths to collide with the same offset
        # filename.  For example:
        #
        #   /some/file/a => _some_file_a
        #   /some/file_a => _some_file_a
        #
        # We add a small CRC string (calculated from before the '_' replacement)
        # to (significantly) reduce the probability of offset filenames
        # colliding under this condition:
        #
        #   /some/file/a => _some_file_a_0744b918
        #   /some/file_a => _some_file_a_287bc0ee
        crc = '{:08x}'.format(abs(zlib.crc32(path.encode('utf-8'))))
        offset_file = '%s_%s' % (path.replace(os.sep, '_'), crc)
        log_file = LogFile(
            logger_name=self.logger.name,
            args=self.args,
            path=path,
            offset_path=os.path.join(self.GetDataDir(), offset_file),
            parse_and_emit_fn=self.ParseAndEmit)
        self.log_files[path] = log_file
        new_log_files.append(log_file)
    return new_log_files

  def ScanLogFilesTask(self):
    """Task to check the glob path for new log files.

    Returns:
      A list of tasks to run (see Main for explanation).  Will include the next
      ScanLogFilesTask, as well as any ProcessLogFileTasks of any newly-detected
      log files.
    """
    self.debug('Scanning for log files after %d seconds elapsed...',
               self.args.new_file_poll_interval)
    new_log_files = self.ScanLogFiles()
    if new_log_files:
      self.info('Scanned for log files, %d new files detected',
                len(new_log_files))
    next_scan = time_utils.MonotonicTime() + self.args.new_file_poll_interval
    new_process_tasks = [
        (0, self.ProcessLogFileTask, [log_file]) for log_file in new_log_files]
    return [(next_scan, self.ScanLogFilesTask, [])] + new_process_tasks

  def ProcessLogFileTask(self, log_file):
    """Task to check a LogFile for new data.

    Returns:
      A list of tasks to run (see Main for explanation).  The only task will be
      the next ProcessLogFileTask for this LogFile.
    """
    self.debug('Processing log file %s...', log_file.path)
    try:
      log_file.AttemptTruncate()
      more_data_available = log_file.ProcessBatch()
      # If we still have more data to process right away, only pause for
      # batch_pause_time.  Otherwise, pause for poll_interval.
      pause_time = (self.args.batch_pause_time if more_data_available
                    else self.args.poll_interval)
    except IOError:
      # We might not have permission to access this file, or there could be
      # some other IO problem.
      self.exception('Exception while accessing file, check permissions')
      pause_time = self.args.error_pause_time
    return [(time_utils.MonotonicTime() + pause_time, self.ProcessLogFileTask,
             [log_file])]

  def Main(self):
    """Main thread of the plugin.

    Runs off a task queue with 3-tuple elements in the format:
      (scheduled_time, task_function, args_list)

    task_function should return a list of tasks, which will be added back onto
    the task queue after running.
    """
    # Kick the task queue off with the initial ScanLogFilesTask.
    task_queue = queue.PriorityQueue()
    task_queue.put((0, self.ScanLogFilesTask, []))

    while not self.IsStopping():
      # Retrieve and run the next scheduled task in the queue.  Add any
      # tasks that the function generates back into the queue.
      _, fn, args = task_queue.get()
      # Remove the '[]' brackets from args list.
      self.debug('Running task %s(%s)...', fn.__name__, str(args)[1:-1])
      for task in fn(*args):
        task_queue.put(task)

      # Retrieve the scheduled time for the next task in the priority queue.
      # Sleep until that task is scheduled.
      next_time, next_fn, next_args = task_queue.queue[0]
      wait_time = max(0, next_time - time_utils.MonotonicTime())
      if wait_time > 0:
        # Remove the '[]' brackets from next_args list.
        self.debug('Need to wait %f sec before running task %s(%s)...',
                   wait_time, next_fn.__name__, str(next_args)[1:-1])
      self.Sleep(wait_time)

  def ParseAndEmit(self, path, offset):
    """Parses lines starting at the given offset, and emits to Instalog.

    Stops when consumed data reaches one of the maximum conditions:

      (1) batch size in bytes >= args.batch_max_bytes
          Protects against case where events are extremely dense.

      (2) number of events in batch >= args.batch_max_count
          Protects against the case where the log file is full of garbage
          (non-parseable data).

    Returns:
      A tuple, where:
        - first element is the offset after processing the current batch of
          events
        - second element is the result from the Emit call (boolean representing
          its success).
    """
    events = []
    line_reader = LineReader(self.logger.name, path, offset)
    event_generator = self.ParseEvents(path, line_reader.Readlines())
    for event in event_generator:
      if event:
        events.append(event)
      self.debug('consumed=%d, len(events)=%d',
                 line_reader.consumed, len(events))
      if line_reader.consumed >= self.args.batch_max_bytes:
        self.info('Stopping after maximum batch bytes %d reached (consumed %d)',
                  self.args.batch_max_bytes, line_reader.consumed)
        break
      if len(events) >= self.args.batch_max_count:
        self.info('Stopping after maximum batch count %d reached',
                  self.args.batch_max_count)
        break
    self.info('Parsed %d events', len(events))
    if events:
      self.store['last_event'] = events[-1].payload
      self.SaveStore()
    return line_reader.offset, self.Emit(events)

  def ParseEvents(self, path, lines):
    """Returns a generator that creates Instalog Event objects.

    Can be overridden in a subclass if necessary.  Should not raise any
    exceptions -- subclasses, beware!

    Generator should generate None if any erroneous data was skipped.  This is
    to give ParseAndEmit a chance to check how many bytes have been processed in
    the current batch, and whether it exceeds self.args.batch_max_bytes.

    Args:
      path: Path to the log file in question.
      lines: A generator which sequentially yields lines from the log file,
             where each line includes trailing \r and \n characters.
    """
    for line in lines:
      try:
        yield self.ParseLine(path, line)
      except Exception:
        self.warning('Ignoring bogus line "%s" in %s due to exception',
                     line.rstrip(), path, exc_info=True)
        yield None

  def ParseLine(self, path, line):
    """Parses a line and returns an Instalog Event object.

    Can be overridden in a subclass if necessary.

    Returns:
      A datatypes.Event object.

    Raises:
      Any exception if the line could not be correctly parsed.
    """
    del path  # We don't use the path of the log file.
    return datatypes.Event(json.loads(line.rstrip()))


class LineReader(log_utils.LoggerMixin):
  """Generates lines of data from the given file starting at the given offset.

  Includes trailing characters \r and \n in yielded strings.  Keeps track of
  the current offset and exposes it as self.offset.
  """
  def __init__(self, logger_name, path, offset):
    # log_utils.LoggerMixin creates shortcut functions for convenience.
    self.logger = logging.getLogger(logger_name)
    self.path = path
    self.offset = offset
    self.consumed = 0

  def Readlines(self):
    """Generates lines of data, keeping track of current offset.

    Returns:
      A tuple, where the first element is the offset after reading the current
      line, and the second element is the current line.
    """
    with open(self.path, 'r') as f:
      f.seek(self.offset)
      for line in f:
        self.offset += len(line)
        self.consumed += len(line)
        self.debug('new_offset=%d, line=%r', self.offset, line.rstrip())
        yield line


class LogFile(log_utils.LoggerMixin):
  """Represents a log file on disk."""

  def __init__(self, logger_name, args, path, offset_path, parse_and_emit_fn):
    # log_utils.LoggerMixin creates shortcut functions for convenience.
    self.logger = logging.getLogger(logger_name)
    self.args = args
    self.path = path
    self.offset_path = offset_path
    self.ParseAndEmit = parse_and_emit_fn

    # Stores the last offset written to disk.
    self.last_written_offset = None

    self.info('Reading offset from %s', self.offset_path)
    self.cur_offset = self.ReadOffset()
    self.info('Starting offset for %s at %d', self.path, self.cur_offset)

  def __repr__(self):
    """Implements repr function for debugging."""
    return 'LogFile(%s)' % self.path

  def GetSize(self):
    """Returns the current size of the log file.

    Resets current offset to 0 if the file is not found.

    Returns:
      File size in bytes.
      None if the file doesn't exist.
    """
    try:
      return os.path.getsize(self.path)
    except OSError:
      # Maybe the file doesn't currently exist, or we don't have access.
      # Reset the offset to zero.
      if self.cur_offset != 0:
        self.info('Input file %s not found, set offset to 0', self.path)
        self.cur_offset = 0
        self.WriteOffset(self.cur_offset)
      return None

  def ProcessBatch(self):
    """If this log file has grown, process the next batch of its data.

    Returns:
      True if more data is available for processing.
      False if all current data has been processed.
    """
    size = self.GetSize()
    if size is None:
      return False

    if size > self.cur_offset:
      self.info('%s progress: %d / %d',
                self.path, self.cur_offset, size)
      new_offset, emit_result = self.ParseAndEmit(
          self.path, offset=self.cur_offset)
      self.debug('new_offset=%s, emit_result=%s',
                 new_offset, emit_result)
      if emit_result:
        self.cur_offset = new_offset
        self.WriteOffset(self.cur_offset)
        self.info('%s progress: %d / %d',
                  self.path, self.cur_offset, size)
      else:
        self.error('Emit failed')
    elif size < self.cur_offset:
      self.info('%s unexpectedly shrunk to %s, resetting from %d to 0',
                self.path, size, self.cur_offset)
      self.cur_offset = 0
      self.WriteOffset(self.cur_offset)

    return self.cur_offset < size

  def AttemptTruncate(self):
    """Attempts to truncate the input file.

    If the following conditions hold true:
      (1) File truncating is enabled (max_bytes is not 0)
      (2) We have read all of the pending new events from the file
      (3) The current size is greater than the maximum allowed file size
    Then attempt truncating the log file.

    Lock the input file, make sure its file size hasn't grown, and truncate
    to 0 bytes.  Write the new offset to disk.

    Returns:
      A boolean representing success of the truncate.
    """
    size = self.GetSize()
    if size is None:
      return False

    if not (self.args.max_bytes > 0 and
            self.cur_offset == size and
            size > self.args.max_bytes):
      return False

    self.info('Input file %s size %d > max size %d, attempt truncate',
              self.path, size, self.args.max_bytes)
    try:
      with file_utils.FileLock(self.path):
        # Make sure the size of the file hasn't grown since our last getsize
        # call outside of the FileLock.
        new_size = os.path.getsize(self.path)
        if self.cur_offset == new_size:
          with open(self.path, 'w') as f:
            f.flush()
            os.fsync(f)
      if self.cur_offset < new_size:
        self.info('File %s already grew to %d bytes, abandon truncate',
                  self.path, new_size)
        return False
    except IOError:
      self.error('Could not acquire file lock on %s, abandon truncate',
                 self.path)
      return False
    else:
      self.info('Truncate successful')
      self.cur_offset = 0
      self.WriteOffset(self.cur_offset)
      # There is a slight possibility that a power failure will occur in between
      # the truncate and here, leaving the offset in a position past the end of
      # the file size.
      return True

  def WriteOffset(self, offset):
    """Writes the current offset to disk."""
    if offset == self.last_written_offset:
      return
    self.last_written_offset = offset
    with file_utils.AtomicWrite(self.offset_path) as f:
      f.write(str(offset))

  def ReadOffset(self):
    """Retrieves the current offset from disk.

    Returns:
      0 if the offset file does not exist.  Otherwise, the integer contained
      within the offset file.
    """
    if not os.path.exists(self.offset_path):
      return 0
    with open(self.offset_path) as f:
      return int(f.read())


if __name__ == '__main__':
  plugin_base.main()
