# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import multiprocessing
import os
import shelve
import time
from datetime import datetime, timedelta

import minijack_common  # pylint: disable=W0611
import factory_common  # pylint: disable=W0611
from cros.factory.utils.shelve_utils import OpenShelfOrBackup
from cros.factory.utils import debug_utils
from datatypes import EventBlob, GenerateEventStreamsFromYaml

EVENT_DELIMITER = '\n---\n'
PREAMBLE_PATTERN = 'EVENT: preamble\n'
LOG_DIR_DATE_FORMAT = '%Y%m%d'
KEY_OFFSET = 'offset'


class WorkerBase(object):
  """The base class of callable workers.

  A worker is an elemental units to process data. It will be delivered to
  multiple processes/machines to complete the job. All its subclasses should
  implement the Process() method.
  """

  def __call__(self, output_writer, input_reader=None, input_done=None):
    """Iterates the input_reader and calls output_writer to process the values.

    Args:
      output_writer: A callable object to process the values.
      input_reader: An iterator to get values; if None, call output_writer once.
      input_done: A callable object which is called when one input is done.
    """
    if input_reader is None:
      input_reader = [None]
    for data in input_reader:
      for result in self.Process(data):
        output_writer(result)
      if input_done:
        input_done()

  def Process(self, dummy_data):
    """A generator to output the processed results of the given data."""
    raise NotImplementedError


class FileScanner(WorkerBase):
  """A callable worker which scans files and yields valid EventBlob's.

  TODO(waihong): Unit tests.

  Properties:
    _scan_dir: Path of the directory to scan.
    _scan_db_file: Path of the scan record db file.
    _scan_period_sec: Period of scanning interval in sec.
    _aborted: Is the process aborted?
    _db: The record db object.
  """

  def __init__(self, scan_dir, scan_db_file, scan_period_sec=30):
    super(FileScanner, self).__init__()
    self._scan_dir = scan_dir
    self._scan_db_file = scan_db_file
    self._scan_period_sec = scan_period_sec
    self._aborted = multiprocessing.Event()
    self._db = self._GetOrCreateDb()

  def __call__(self, output_writer, input_reader=None, input_done=None):
    assert input_reader is None
    assert input_done is None
    super(FileScanner, self).__call__(output_writer)

  def Stop(self):
    """Stops scanning files."""
    self._aborted.set()

  def Process(self, dummy_data):
    """A forever loop to generate EventBlob's."""
    last_scan_time = 0
    while True:
      next_scan_time = last_scan_time + self._scan_period_sec
      current_time = time.time()
      if current_time < next_scan_time:
        # Wait the next scan, or return immediately when abort.
        if self._aborted.wait(next_scan_time - current_time):
          return
      last_scan_time = time.time()

      # Sorts dirs by their names, as its modification time is changed when
      # their files inside are changed/added/removed. Their names are more
      # reliable than the time.
      dir_name = lambda w: w[0]
      for dir_path, _, file_names in sorted(os.walk(self._scan_dir),
                                            key=dir_name):
        # Sorts files by their modification time.
        file_mtime = lambda f: os.lstat(os.path.join(dir_path, f)).st_mtime
        for file_name in sorted(file_names, key=file_mtime):
          full_path = os.path.join(dir_path, file_name)
          short_path = os.path.relpath(full_path, self._scan_dir)
          # Skip non-valid files.
          if not os.path.isfile(full_path):
            continue
          # The file changes since the last time.
          if (not self._db.has_key(short_path) or
              self._db[short_path][KEY_OFFSET] != os.path.getsize(full_path)):
            try:
              chunk = self._ScanEventLog(short_path)
            except:  # pylint: disable=W0702
              logging.info(short_path + ': ' +
                           debug_utils.FormatExceptionOnly())
            if chunk:
              logging.info('Get new event logs (%s, %d bytes)',
                           short_path, len(chunk))
              yield EventBlob({'log_name': short_path}, chunk)
              self._UpdateRecord(short_path, len(chunk))
          # Skip remaining when abort.
          if self._aborted.is_set():
            return

  def _GetOrCreateDb(self):
    """Gets the database or recreate one if exception occurs."""
    try:
      db = OpenShelfOrBackup(self._scan_db_file)
    except:  # pylint: disable=W0702
      logging.exception('Corrupted database, recreating')
      os.unlink(self._scan_db_file)
      db = shelve.open(self._scan_db_file)
    return db

  def _UpdateRecord(self, log_name, handled_size):
    """Updates the DB record by handled_size bytes"""
    log_state = self._db.setdefault(log_name, {KEY_OFFSET: 0})
    log_state[KEY_OFFSET] += handled_size
    self._db[log_name] = log_state
    self._db.sync()

  def _ScanEventLog(self, log_name):
    """Scans new generated event log."""
    log_state = self._db.setdefault(log_name, {KEY_OFFSET: 0})
    with open(os.path.join(self._scan_dir, log_name)) as f:
      f.seek(log_state[KEY_OFFSET])
      chunk = f.read()
      last_separator = chunk.rfind(EVENT_DELIMITER)
      # No need to proceed if available chunk is empty.
      if last_separator == -1:
        return None
      chunk = chunk[0:(last_separator + len(EVENT_DELIMITER))]
      return chunk


class IdentityWorker(WorkerBase):
  """A callable worker to simply put the data from input to output."""

  def Process(self, data):
    yield data


class EventLoadingWorker(WorkerBase):
  """A callable worker for loading events and converting to Python objects.

  Properties:
    _log_dir: The path of the event log directory.
  """

  def __init__(self, log_dir):
    super(EventLoadingWorker, self).__init__()
    self._log_dir = log_dir

  def Process(self, blob):
    """Generates event streams from an given event blob."""
    start_time = time.time()
    log_name = blob.metadata['log_name']
    for stream in GenerateEventStreamsFromYaml(blob.metadata, blob.chunk):
      # TODO(waihong): Abstract the filesystem access.
      if not stream.preamble or not stream.preamble.get('device_id'):
        log_path = os.path.join(self._log_dir, log_name)
        stream.preamble = self.GetLastPreambleFromFile(log_path)
      if not stream.preamble and log_name.startswith('logs.'):
        # Try to find the preamble from the same file in the yesterday log dir.
        (today_dir, rest_path) = log_name.split('/', 1)
        yesterday_dir = self.GetYesterdayLogDir(today_dir)
        if yesterday_dir:
          log_path = os.path.join(self._log_dir, yesterday_dir, rest_path)
          if os.path.isfile(log_path):
            stream.preamble = self.GetLastPreambleFromFile(log_path)

      if not stream.preamble:
        logging.warn('Drop the event stream without preamble, log file: %s',
                     log_name)
      else:
        logging.info('YAML to Python obj (%s, %.3f sec)',
                     stream.metadata.get('log_name'),
                     time.time() - start_time)
        yield stream

  @staticmethod
  def GetLastPreambleFromFile(file_path):
    """Gets the last preamble event dict from a given file path.

    Args:
      file_path: The path of the log file.

    Returns:
      A dict of the preamble event. None if not found.
    """
    # TODO(waihong): Optimize it using a cache.
    try:
      text = open(file_path).read()
    except:  # pylint: disable=W0702
      logging.exception('Error on reading log file %s: %s',
                        file_path,
                        debug_utils.FormatExceptionOnly())
      return None

    preamble_pos = text.rfind(PREAMBLE_PATTERN)
    if preamble_pos == -1:
      return None
    end_pos = text.find(EVENT_DELIMITER, preamble_pos)
    if end_pos == -1:
      return None
    streams = GenerateEventStreamsFromYaml(None, text[preamble_pos:end_pos])
    stream = next(streams, None)
    if stream is not None:
      return stream.preamble
    else:
      return None

  @staticmethod
  def GetYesterdayLogDir(today_dir):
    """Gets the dir name for one day before.

    Args:
      today_dir: A string of dir name.

    Returns:
      A string of dir name for one day before today_dir. None if not valid.
    """
    try:
      today = datetime.strptime(today_dir, 'logs.' + LOG_DIR_DATE_FORMAT)
    except ValueError:
      logging.warn('The path is not a valid format with date: %s', today_dir)
      return None
    return 'logs.' + (today - timedelta(days=1)).strftime(LOG_DIR_DATE_FORMAT)
