# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import logging
import os
import shelve
import threading

from cros.factory.test.env import paths
from cros.factory.test import event_log
from cros.factory.utils import debug_utils
from cros.factory.utils import shelve_utils

EVENT_SEPARATOR = '\n---\n'
KEY_OFFSET = 'offset'
EVENT_LOG_DB_FILE = os.path.join(paths.DATA_STATE_DIR, 'event_log_db')


class ScanException(Exception):
  pass


class Chunk(collections.namedtuple('Chunk', 'log_name chunk pos')):
  """Chunk scanned by the log watcher.

  Properties:
    log_name: Name of the log
    chunk: Value of the chunk
    pos: Position of the chunk within the file
  """

  def __str__(self):
    return 'Chunk(log_name=%r, len=%s, pos=%d)' % (
        self.log_name, len(self.chunk), self.pos)


class EventLogWatcher:
  """An object watches event log and invokes a callback as new logs appear."""

  def __init__(self,
               watch_period_sec=30,
               event_log_dir=event_log.EVENT_LOG_DIR,
               event_log_db_file=EVENT_LOG_DB_FILE,
               handle_event_logs_callback=None,
               num_log_per_callback=0):
    """Constructor.

    Args:
      watch_period_sec: The time period in seconds between consecutive
          watches.
      event_log_db_file: The file in which to store the DB of event logs,
          or None to use sync markers instead (see event_log.py).
      handle_event_logs_callback: The callback to trigger after new event logs
          found. This is a function which accepts two arguments:
              chunks: A list of Chunk objects.
              periodic: True if this event log handling is periodic.
                  False if this event log handling is requested by user calling
                  FlushEventLogs.
      num_log_per_callback: The maximum number of log files per callback, or 0
          for unlimited number of log files.
    """
    self._watch_period_sec = watch_period_sec
    self._event_log_dir = event_log_dir
    self._event_log_db_file = event_log_db_file
    self._handle_event_logs_callback = handle_event_logs_callback
    self._num_log_per_callback = num_log_per_callback
    self._watch_thread = None
    self._aborted = threading.Event()
    self._kick = threading.Event()
    self._scan_lock = threading.Lock()

    self._use_sync_markers = event_log_db_file is None
    self._db = {} if self._use_sync_markers else self.GetOrCreateDb()

  def StartWatchThread(self):
    """Starts a thread to watch event logs."""
    logging.info('Watching event logs...')
    self._watch_thread = threading.Thread(target=self.WatchForever,
                                          name='EventLogWatcher')
    self._watch_thread.start()

  def IsThreadStarted(self):
    """Returns True if the thread is currently running."""
    return self._watch_thread is not None

  def IsScanning(self):
    """Returns True if currently scanning (i.e., the lock is held)."""
    if self._scan_lock.acquire(blocking=False):
      self._scan_lock.release()
      return False
    return True

  def FlushEventLogs(self):
    """Flushes event logs.

    Call ScanEventLogs and with suppress_error flag to false.
    """
    with self._scan_lock:
      self.ScanEventLogs(False, False)

  def _CallEventLogHandler(self, chunks, suppress_error, periodic):
    """Invoke event log handler callback.

    Args:
      chunks: A list of Chunks.
      suppress_error: if set to true then any exception from handle event
          log callback will be ignored.
      periodic: This is a periodic event scanning, not by request.

    Raises:
      ScanException: if upload handler throws exception.
    """
    try:
      if self._handle_event_logs_callback is not None:
        self._handle_event_logs_callback(chunks, periodic)
      if self._use_sync_markers:
        # Update the sync marker in each chunk.
        for chunk in chunks:
          last_sync_marker = chunk.chunk.rfind(event_log.SYNC_MARKER_SEARCH)
          if not last_sync_marker:
            continue
          with open(os.path.join(self._event_log_dir, chunk.log_name),
                    'r+') as f:
            f.seek(chunk.pos + last_sync_marker)
            f.write(event_log.SYNC_MARKER_REPLACE)
            f.flush()
            os.fdatasync(f)

    except Exception:
      if suppress_error:
        logging.debug('Upload handler error')
      else:
        raise ScanException(debug_utils.FormatExceptionOnly())
      return

    try:
      # Update log state to db.
      for chunk in chunks:
        log_state = self._db.setdefault(chunk.log_name, {KEY_OFFSET: 0})
        log_state[KEY_OFFSET] += len(chunk.chunk)
        self._db[chunk.log_name] = log_state
      if not self._use_sync_markers:
        self._db.sync()
    except Exception:
      if suppress_error:
        logging.debug('Upload handler error')
      else:
        raise ScanException(debug_utils.FormatExceptionOnly())

  def ScanEventLogs(self, suppress_error=True, periodic=False):
    """Scans event logs.

    Args:
      suppress_error: if set to true then any exception from handle event
          log callback will be ignored.
      periodic: This is a periodic event scanning, not by request.

    Raise:
      ScanException: if at least one ScanEventLog call throws exception.
    """
    if not os.path.exists(self._event_log_dir):
      logging.warning('Event log directory %s does not exist yet',
                      self._event_log_dir)
      return

    chunks = []

    # Sorts dirs by their names, as its modification time is changed when
    # their files inside are changed/added/removed. Their names are more
    # reliable than the time.
    dir_name = lambda w: w[0]
    for dir_path, _, file_names in sorted(os.walk(self._event_log_dir),
                                          key=dir_name):
      # Sorts files by their modification time.
      file_mtime = lambda f, p=dir_path: os.lstat(os.path.join(p, f)).st_mtime
      for file_name in sorted(file_names, key=file_mtime):
        file_path = os.path.join(dir_path, file_name)
        if not os.path.isfile(file_path):
          continue
        relative_path = os.path.relpath(file_path, self._event_log_dir)
        if (relative_path not in self._db or
            self._db[relative_path][KEY_OFFSET] != os.path.getsize(file_path)):
          try:
            chunk_info = self.ScanEventLog(relative_path)
            if chunk_info is not None:
              chunks.append(chunk_info)
          except Exception:
            msg = relative_path + ': ' + debug_utils.FormatExceptionOnly()
            if suppress_error:
              logging.info(msg)
            else:
              raise ScanException(msg)
        if (self._num_log_per_callback and
            len(chunks) >= self._num_log_per_callback):
          self._CallEventLogHandler(chunks, suppress_error, periodic)
          chunks = []
          # Skip remaining when abort. We don't want to wait too long for the
          # remaining finished.
          if self._aborted.isSet():
            return

    if chunks:
      self._CallEventLogHandler(chunks, suppress_error, periodic)

  def StopWatchThread(self):
    """Stops the event logs watching thread."""
    self._aborted.set()
    self._kick.set()
    self._watch_thread.join()
    self._watch_thread = None
    logging.info('Stopped watching.')
    self.Close()

  def KickWatchThread(self):
    self._kick.set()

  def Close(self):
    """Closes the database."""
    if not self._use_sync_markers:
      self._db.close()

  def WatchForever(self):
    """Watches event logs forever."""
    while True:
      # Flush the event logs once every watch period.
      self._kick.wait(self._watch_period_sec)
      self._kick.clear()
      if self._aborted.isSet():
        return
      try:
        with self._scan_lock:
          self.ScanEventLogs(True, True)
      except Exception:
        logging.exception('Error in event log watcher thread')

  def GetOrCreateDb(self):
    """Gets the database or recreate one if exception occurs."""
    assert not self._use_sync_markers

    try:
      db = shelve_utils.OpenShelfOrBackup(self._event_log_db_file)
    except Exception:
      logging.exception('Corrupted database, recreating')
      os.unlink(self._event_log_db_file)
      db = shelve.open(self._event_log_db_file)
    return db

  def ScanEventLog(self, log_name):
    """Scans new generated event log.

    Scans event logs in given file path and flush to our database.
    If the log name has no record, create an empty event log for it.

    Args:
      log_name: name of the log file.
    """
    log_state = self._db.get(log_name)
    if not log_state:
      # We haven't seen this file yet since starting up.
      offset = 0
      if self._use_sync_markers:
        # Read in the file and set offset from the last sync marker.
        with open(os.path.join(self._event_log_dir, log_name),
                  encoding='utf-8') as f:
          contents = f.read()
        # Set the offset to just after the last instance of
        # "\n#S\n---\n".
        replace_pos = contents.rfind(event_log.SYNC_MARKER_REPLACE)
        if replace_pos == -1:
          # Not found; start at the beginning.
          offset = 0
        else:
          offset = replace_pos + len(event_log.SYNC_MARKER_REPLACE)
      else:
        # No sync markers; start from the beginning.
        offset = 0
      log_state = {KEY_OFFSET: offset}
      self._db[log_name] = log_state

    with open(os.path.join(self._event_log_dir, log_name),
              encoding='utf-8') as f:
      f.seek(log_state[KEY_OFFSET])

      chunk = f.read()
      last_separator = chunk.rfind(EVENT_SEPARATOR)
      # No need to proceed if available chunk is empty.
      if last_separator == -1:
        return None

      chunk = chunk[0:(last_separator + len(EVENT_SEPARATOR))]
      return Chunk(log_name, chunk, log_state[KEY_OFFSET])

  def GetEventLog(self, log_name):
    """Gets the log for given log name."""
    return self._db.get(log_name)
