#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import shelve
import threading

from cros.factory import event_log
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.utils.shelve_utils import OpenShelfOrBackup

EVENT_SEPARATOR = '\n---\n'
KEY_OFFSET = 'offset'
EVENT_LOG_DB_FILE = os.path.join(factory.get_state_root(), 'event_log_db')


class ScanException(Exception):
  pass


class EventLogWatcher(object):
  '''An object watches event log and invokes a callback as new logs appear.'''

  def __init__(self, watch_period_sec=30,
             event_log_dir=event_log.EVENT_LOG_DIR,
             event_log_db_file=EVENT_LOG_DB_FILE,
             handle_event_logs_callback=None,
             num_log_per_callback=0):
    '''Constructor.

    Args:
      watch_period_sec: The time period in seconds between consecutive
          watches.
      event_log_db_file: The file in which to store the DB of event logs.
      handle_event_logs__callback: The callback to trigger after new event logs
          found.
      num_log_per_callback: The maximum number of log files per callback, or 0
          for unlimited number of log files.
    '''
    self._watch_period_sec = watch_period_sec
    self._event_log_dir = event_log_dir
    self._event_log_db_file = event_log_db_file
    self._handle_event_logs_callback = handle_event_logs_callback
    self._num_log_per_callback = num_log_per_callback
    self._watch_thread = None
    self._aborted = threading.Event()
    self._kick = threading.Event()
    self._db = self.GetOrCreateDb()
    self._scan_lock = threading.Lock()

  def StartWatchThread(self):
    '''Starts a thread to watch event logs.'''
    logging.info('Watching event logs...')
    self._watch_thread = threading.Thread(target=self.WatchForever,
                                          name='EventLogWatcher')
    self._watch_thread.start()

  def IsThreadStarted(self):
    '''Returns True if the thread is currently running.'''
    return self._watch_thread is not None

  def IsScanning(self):
    '''Returns True if currently scanning (i.e., the lock is held).'''
    if self._scan_lock.acquire(blocking=False):
      self._scan_lock.release()
      return False
    else:
      return True

  def FlushEventLogs(self):
    '''Flushes event logs.

    Call ScanEventLogs and with suppress_error flag to false.
    '''
    with self._scan_lock:
      self.ScanEventLogs(False)

  def _CallEventLogHandler(self, chunk_info_list, suppress_error):
    '''Invoke event log handler callback.

    Args:
      chunk_info_list: A list of tuple (log_name, chunk).
      suppress_error: if set to true then any exception from handle event
          log callback will be ignored.

    Raises:
      ScanException: if upload handler throws exception.
    '''
    try:
      if self._handle_event_logs_callback is not None:
        self._handle_event_logs_callback(chunk_info_list)
    except: # pylint: disable=W0702
      if suppress_error:
        logging.exception('Upload handler error')
      else:
        raise ScanException(utils.FormatExceptionOnly())
      return

    try:
      # Update log state to db.
      for log_name, chunk in chunk_info_list:
        log_state = self._db.setdefault(log_name, {KEY_OFFSET: 0})
        log_state[KEY_OFFSET] += len(chunk)
        self._db[log_name] = log_state
      self._db.sync()
    except: # pylint: disable=W0702
      if suppress_error:
        logging.exception('Upload handler error')
      else:
        raise ScanException(utils.FormatExceptionOnly())

  def ScanEventLogs(self, suppress_error=True):
    '''Scans event logs.

    Args:
      suppress_error: if set to true then any exception from handle event
          log callback will be ignored.

    Raise:
      ScanException: if at least one ScanEventLog call throws exception.
    '''
    if not os.path.exists(self._event_log_dir):
      logging.warn("Event log directory %s does not exist yet",
                   self._event_log_dir)
      return

    chunk_info_list = []

    # Sorts dirs by their names, as its modification time is changed when
    # their files inside are changed/added/removed. Their names are more
    # reliable than the time.
    dir_name = lambda w: w[0]
    for dir_path, _, file_names in sorted(os.walk(self._event_log_dir),
                                          key=dir_name):
      # Sorts files by their modification time.
      file_mtime = lambda f: os.lstat(os.path.join(dir_path, f)).st_mtime
      for file_name in sorted(file_names, key=file_mtime):
        file_path = os.path.join(dir_path, file_name)
        if not os.path.isfile(file_path):
          continue
        relative_path = os.path.relpath(file_path, self._event_log_dir)
        if (not self._db.has_key(relative_path) or
            self._db[relative_path][KEY_OFFSET] != os.path.getsize(file_path)):
          try:
            chunk_info = self.ScanEventLog(relative_path)
            if chunk_info is not None:
              chunk_info_list.append(chunk_info)
          except:  # pylint: disable=W0702
            msg = relative_path + ': ' + utils.FormatExceptionOnly()
            if suppress_error:
              logging.info(msg)
            else:
              raise ScanException(msg)
        if (self._num_log_per_callback and
            len(chunk_info_list) >= self._num_log_per_callback):
          self._CallEventLogHandler(chunk_info_list, suppress_error)
          chunk_info_list = []
          # Skip remaining when abort. We don't want to wait too long for the
          # remaining finished.
          if self._aborted.isSet():
            return

    if chunk_info_list:
      self._CallEventLogHandler(chunk_info_list, suppress_error)


  def StopWatchThread(self):
    '''Stops the event logs watching thread.'''
    self._aborted.set()
    self._kick.set()
    self._watch_thread.join()
    self._watch_thread = None
    logging.info('Stopped watching.')
    self.Close()

  def KickWatchThread(self):
    self._kick.set()

  def Close(self):
    '''Closes the database.'''
    self._db.close()

  def WatchForever(self):
    '''Watches event logs forever.'''
    while True:
      # Flush the event logs once every watch period.
      self._kick.wait(self._watch_period_sec)
      self._kick.clear()
      if self._aborted.isSet():
        return
      try:
        with self._scan_lock:
          self.ScanEventLogs()
      except:  # pylint: disable=W0702
        logging.exception('Error in event log watcher thread')

  def GetOrCreateDb(self):
    '''Gets the database or recreate one if exception occurs.'''
    try:
      db = OpenShelfOrBackup(self._event_log_db_file)
    except:  # pylint: disable=W0702
      logging.exception('Corrupted database, recreating')
      os.unlink(self._event_log_db_file)
      db = shelve.open(self._event_log_db_file)
    return db

  def ScanEventLog(self, log_name):
    '''Scans new generated event log.

    Scans event logs in given file path and flush to our database.
    If the log name has no record, create an empty event log for it.

    Args:
      log_name: name of the log file.
    '''
    log_state = self._db.setdefault(log_name, {KEY_OFFSET: 0})

    with open(os.path.join(self._event_log_dir, log_name)) as f:
      f.seek(log_state[KEY_OFFSET])

      chunk = f.read()
      last_separator = chunk.rfind(EVENT_SEPARATOR)
      # No need to proceed if available chunk is empty.
      if last_separator == -1:
        return

      chunk = chunk[0:(last_separator + len(EVENT_SEPARATOR))]
      return (log_name, chunk)

  def GetEventLog(self, log_name):
    '''Gets the log for given log name.'''
    return self._db.get(log_name)
