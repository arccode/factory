# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import time
from datetime import datetime, timedelta

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.minijack.datatypes import GenerateEventStreamsFromYaml


EVENT_DELIMITER = '---\n'
PREAMBLE_PATTERN = 'EVENT: preamble\n'
LOG_DIR_DATE_FORMAT = '%Y%m%d'


class WorkerBase(object):
  """The base class of callable workers.

  A worker is an elemental units to process data. It will be delivered to
  multiple processes/machines to complete the job. All its subclasses should
  implement the Process() method.
  """
  def __call__(self, input_reader, output_writer, input_done=None):
    """Iterates the input_reader and calls output_write to process the values.

    Args:
      input_reader: An iterator to get values.
      output_write: A callable object to process the values.
      input_done: A callable object which is called when one input is done.
    """
    for data in input_reader:
      for result in self.Process(data):
        output_writer(result)
      input_done()

  def Process(self, dummy_data):
    """A generator to output the processed results of the given data."""
    raise NotImplementedError


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
                        utils.FormatExceptionOnly())
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
