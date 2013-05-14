# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import time
from datetime import datetime, timedelta

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.minijack.datatypes import EventStream


EVENT_DELIMITER = '---\n'
LOG_DIR_DATE_FORMAT = '%Y%m%d'


class WorkerBase(object):
  """The base class of callable workers.

  A worker is an elemental units to process data. It will be delivered to
  multiple processes/machines to complete the job. All its subclasses should
  implement the Process() method.
  """
  def __call__(self, input_reader, output_writer):
    """Iterates the input_reader and calls output_write to process the values.

    Args:
      input_reader: An iterator to get values.
      output_reader: A callable object to process the values.
    """
    for data in input_reader:
      for result in self.Process(data):
        output_writer(result)

  def Process(self, dummy_data):
    """A generator to output the processed results of the given data."""
    raise NotImplementedError


class IdentityWorker(WorkerBase):
  """A callable worker to simply put the data from input to output."""
  def Process(self, data):
    yield data


class EventLoadingWorker(WorkerBase):
  """A callable worker for loading events and converting to Python objects.

  TODO(waihong): Unit tests.

  Properties:
    _log_dir: The path of the event log directory.
  """
  def __init__(self, log_dir):
    super(EventLoadingWorker, self).__init__()
    self._log_dir = log_dir

  def Process(self, blob):
    """Generates an event stream from an given event blob."""
    yield self._ConvertToEventStream(blob)

  def _GetPreambleFromLogFile(self, log_path):
    """Gets the preamble event dict from a given log file path."""
    def ReadLinesUntil(lines, delimiter):
      """A generator to yield the lines iterator until the delimiter matched."""
      for line in lines:
        if line == delimiter:
          break
        else:
          yield line

    # TODO(waihong): Optimize it using a cache.
    try:
      with open(log_path) as lines:
        # Only read the first event, i.e. the lines until EVENT_DELIMITER.
        yaml_str = ''.join(ReadLinesUntil(lines, EVENT_DELIMITER))
    except:  # pylint: disable=W0702
      logging.exception('Error on reading log file %s: %s',
                        log_path,
                        utils.FormatExceptionOnly())
      return None
    stream = EventStream(None, yaml_str)
    return stream.preamble

  def _ConvertToEventStream(self, blob):
    """Callback for event log watcher."""
    start_time = time.time()
    log_name = blob.metadata['log_name']
    stream = EventStream(blob.metadata, blob.chunk)

    # TODO(waihong): Abstract the filesystem access.
    if not stream.preamble:
      log_path = os.path.join(self._log_dir, log_name)
      stream.preamble = self._GetPreambleFromLogFile(log_path)
    if not stream.preamble and log_name.startswith('logs.'):
      # Try to find the preamble from the same file in the yesterday log dir.
      (today_dir, rest_path) = log_name.split('/', 1)
      yesterday_dir = GetYesterdayLogDir(today_dir)
      if yesterday_dir:
        log_path = os.path.join(self._log_dir, yesterday_dir, rest_path)
        if os.path.isfile(log_path):
          stream.preamble = self._GetPreambleFromLogFile(log_path)

    if not stream.preamble:
      logging.warn('Drop the event stream without preamble, log file: %s',
                   log_name)
      return None
    else:
      logging.info('YAML to Python obj (%s, %.3f sec)',
                   stream.metadata.get('log_name'),
                   time.time() - start_time)
      return stream


def GetYesterdayLogDir(today_dir):
  """Gets the dir name for one day before.

  Args:
    today_dir: A string of dir name.

  Returns:
    A string of dir name for one day before today_dir.

  >>> GetYesterdayLogDir('logs.20130417')
  'logs.20130416'
  >>> GetYesterdayLogDir('logs.no_date')
  >>> GetYesterdayLogDir('invalid')
  >>> GetYesterdayLogDir('logs.20130301')
  'logs.20130228'
  >>> GetYesterdayLogDir('logs.20140101')
  'logs.20131231'
  """
  try:
    today = datetime.strptime(today_dir, 'logs.' + LOG_DIR_DATE_FORMAT)
  except ValueError:
    logging.warn('The path is not a valid format with date: %s', today_dir)
    return None
  return 'logs.' + (today - timedelta(days=1)).strftime(LOG_DIR_DATE_FORMAT)
