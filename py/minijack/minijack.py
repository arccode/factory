#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
Minijack is a real-time log converter for on-site factory log analysis.

It runs in the same device of the shopfloor service and keeps monitoring
the event log directory. When new logs come, it converts these event logs
and dumps them to a database, such that factory engineers can easily analyse
these logs using SQL queries.

This file starts a Minijack process which services forever until an user
presses Ctrl-C to terminate it. To use it, invoke as a standalone program:
  ./minijack [options]
'''

import logging
import multiprocessing
import optparse
import os
import pprint
import re
import signal
import sys
import time
import yaml
from datetime import datetime, timedelta

import factory_common  # pylint: disable=W0611
from cros.factory.event_log_watcher import EventLogWatcher
from cros.factory.minijack import db
from cros.factory.test import utils

SHOPFLOOR_DATA_DIR = 'shopfloor_data'
EVENT_LOG_DB_FILE = 'event_log_db'
MINIJACK_DB_FILE = 'minijack_db'

DEFAULT_WATCH_INTERVAL = 30  # seconds
DEFAULT_JOB_NUMBER = 6
DEFAULT_QUEUE_SIZE = 10
EVENT_DELIMITER = '---\n'
LOG_DIR_DATE_FORMAT = '%Y%m%d'

# The following YAML strings needs further handler. So far we just simply
# remove them. It works well now, while tuples are treated as lists, unicodes
# are treated as strings, objects are dropped.
# TODO(waihong): Use yaml.add_multi_constructor to handle them.
YAML_STR_BLACKLIST = (
    r'( !!python/tuple| !!python/unicode| !!python/object[A-Za-z_.:/]+)')

class EventStream(list):
  '''Event Stream Structure.

  An EventStream is a list to store multiple non-preamble events, which share
  the same preamble event.

  Properties:
    preamble: The dict of the preamble event.
  '''
  def __init__(self, yaml_str):
    '''Initializer.

    Args:
      yaml_str: The string contains multiple yaml-formatted events.
    '''
    super(EventStream, self).__init__()
    self.preamble = None
    self._LoadFromYaml(yaml_str)

  def _LoadFromYaml(self, yaml_str):
    '''Loads from multiple yaml-formatted events with delimiters.

    Args:
      yaml_str: The string contains multiple yaml-formatted events.
    '''
    # Some un-expected patterns appear in the log. Remove them.
    yaml_str = re.sub(YAML_STR_BLACKLIST, '', yaml_str)
    try:
      for event in yaml.safe_load_all(yaml_str):
        if not event:
          continue
        if 'EVENT' not in event:
          logging.warn('The event dict is invalid, no EVENT tag:\n%s.',
                       pprint.pformat(event))
          continue
        if event['EVENT'] == 'preamble':
          self.preamble = event
        else:
          self.append(event)
    except yaml.YAMLError, e:
      logging.exception('Error on parsing the yaml string "%s": %s',
                        yaml_str, e)

class EventPacket(object):
  '''Event Packet Structure.

  An EventPacket is a non-preamble event combined with its preamble. It is
  used as an argument to pass to the exporters.

  Properties:
    preamble: The dict of the preamble event.
    event: The dict of the non-preamble event.
  '''
  def __init__(self, preamble, event):
    self.preamble = preamble
    self.event = event

  @staticmethod
  def FlattenAttr(attr):
    '''Generator of flattened attributes.

    Args:
      attr: The attr dict/list which may contains multi-level dicts/lists.

    Yields:
      A tuple (path_str, leaf_value).
    '''
    def _FlattenAttr(attr):
      if isinstance(attr, dict):
        for key, val in attr.iteritems():
          for path, leaf in _FlattenAttr(val):
            yield [key] + path, leaf
      elif isinstance(attr, list):
        for index, val in enumerate(attr):
          for path, leaf in _FlattenAttr(val):
            yield [str(index)] + path, leaf
      else:
        # The leaf node.
        yield [], attr

    # Join the path list using '.'.
    return (('.'.join(k), v) for k, v in _FlattenAttr(attr))

  def FindAttrContainingKey(self, key):
    '''Finds the attr in the event that contains the given key.

    Args:
      key: A string of key.

    Returns:
      The dict inside the event that contains the given key.
    '''
    def _FindContainingDictForKey(deep_dict, key):
      if isinstance(deep_dict, dict):
        if key in deep_dict.iterkeys():
          # Found, return its parent.
          return deep_dict
        else:
          # Try its children.
          for val in deep_dict.itervalues():
            result = _FindContainingDictForKey(val, key)
            if result:
              return result
      elif isinstance(deep_dict, list):
        # Try its children.
        for val in deep_dict:
          result = _FindContainingDictForKey(val, key)
          if result:
            return result
      # Not found.
      return None

    return _FindContainingDictForKey(self.event, key)

class EventReceiver(object):
  '''Event Receiver which invokes the proper exporters when events is received.

  TODO(waihong): Unit tests.

  Properties:
    _all_exporters: A list of all registered exporters.
    _event_invokers: A dict of lists, where the event id as key and the list
                     of handler functions as value.
  '''
  def __init__(self):
    self._all_exporters = []
    self._event_invokers = {}

  def RegisterExporter(self, exporter):
    '''Registers a exporter object.'''
    logging.debug('Register the exporter: %s', exporter)
    self._all_exporters.append(exporter)
    # Search all Handle_xxx() methods in the exporter instance.
    for handler_name in dir(exporter):
      if handler_name.startswith('Handle_'):
        event_id = handler_name.split('_', 1)[1]
        # Create a new list if not present.
        if event_id not in self._event_invokers:
          self._event_invokers[event_id] = []
        # Add the handler function to the list.
        handler_func = getattr(exporter, handler_name)
        self._event_invokers[event_id].append(handler_func)

    logging.debug('Call the setup method of the exporter: %s', exporter)
    exporter.Setup()

  def ReceiveEventStream(self, stream):
    '''Callback for an event stream received.'''
    start_time = time.time()
    for event in stream:
      packet = EventPacket(stream.preamble, event)
      self.ReceiveEventPacket(packet)
    logging.info('Dumped to database (%s, %d events, %.3f sec)',
                 stream.preamble.get('filename'),
                 len(stream),
                 time.time() - start_time)

  def ReceiveEventPacket(self, packet):
    '''Callback for an event packet received.'''
    # Event id 'all' is a special case, which means the handlers accepts
    # all kinds of events.
    for event_id in ('all', packet.event['EVENT']):
      invokers = self._event_invokers.get(event_id, [])
      for invoker in invokers:
        try:
          invoker(packet)
        except:  # pylint: disable=W0702
          logging.exception('Error on invoking the exporter: %s',
                            utils.FormatExceptionOnly())

class EventReceivingWorker(object):
  '''A callable worker for receiving events and dumping to database.

  TODO(waihong): Unit tests.

  Properties:
    _database: The database object.
    _receiver: The event receiver object.
  '''
  def __init__(self, database):
    self._database = database

    # TODO(waihong): Make the exporter module an argument for customization.
    self._receiver = EventReceiver()
    logging.debug('Load all the default exporters')
    # Find all exporter modules named xxx_exporter.
    exporter_pkg = __import__('cros.factory.minijack',
                              fromlist=['exporters']).exporters
    for exporter_name in dir(exporter_pkg):
      if exporter_name.endswith('_exporter'):
        exporter_module = getattr(exporter_pkg, exporter_name)
        # Class name conversion: XxxExporter.
        class_name = ''.join([s.capitalize() for s in exporter_name.split('_')])
        exporter_class = getattr(exporter_module, class_name)
        exporter = exporter_class(self._database)
        # Register the exporter instance.
        self._receiver.RegisterExporter(exporter)

  # TODO(waihong): Abstract the input as a general iterator instead of a queue.
  def __call__(self, input_queue):
    '''Receives an event stream from the input queue and dumps to database.'''
    for stream in iter(input_queue.get, None):
      self._receiver.ReceiveEventStream(stream)
      input_queue.task_done()
      # Note that it is not a real idle. The event-log-watcher or the
      # event-loading-worker may be processing new event logs but have
      # not put them in the queue yet.
      # TODO(waihong): Do an accurate check to confirm the idle state.
      if input_queue.empty():
        logging.info('Minijack is idle.')

class EventBlob(object):
  '''A structure to wrap the information returned from event log watcher.

  Properties:
    metadata: A dict to keep the metadata.
    chunk: A byte-list to store the orignal event data.
  '''
  def __init__(self, metadata, chunk):
    self.metadata = metadata
    self.chunk = chunk

class EventLoadingWorker(object):
  '''A callable worker for loading events and converting to Python objects.

  TODO(waihong): Unit tests.

  Properties:
    _log_dir: The path of the event log directory.
  '''
  def __init__(self, log_dir):
    self._log_dir = log_dir

  # TODO(waihong): Abstract the input as a general iterator instead of a queue.
  def __call__(self, input_queue, output_queue):
    '''Loads an event blob from the queue and converts to an event stream.'''
    for blob in iter(input_queue.get, None):
      stream = self._ConvertToEventStream(blob)
      if stream:
        output_queue.put(stream)
      input_queue.task_done()

  def _GetPreambleFromLogFile(self, log_path):
    '''Gets the preamble event dict from a given log file path.'''
    def ReadLinesUntil(lines, delimiter):
      '''A generator to yield the lines iterator until the delimiter matched.'''
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
    stream = EventStream(yaml_str)
    return stream.preamble

  def _ConvertToEventStream(self, blob):
    '''Callback for event log watcher.'''
    start_time = time.time()
    log_name = blob.metadata['log_name']
    stream = EventStream(blob.chunk)

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
                   stream.preamble.get('filename'),
                   time.time() - start_time)
      return stream

def GetYesterdayLogDir(today_dir):
  '''Get the dir name for one day before.

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
  '''
  try:
    today = datetime.strptime(today_dir, 'logs.' + LOG_DIR_DATE_FORMAT)
  except ValueError:
    logging.warn('The path is not a valid format with date: %s', today_dir)
    return None
  return 'logs.' + (today - timedelta(days=1)).strftime(LOG_DIR_DATE_FORMAT)

class Minijack(object):
  '''The main Minijack flow.

  TODO(waihong): Unit tests.

  Properties:
    _database: The database object.
    _log_watcher: The event log watcher.
    _worker_processes: A list of worker processes.
    _event_blob_queue: The queue storing event blobs.
    _event_stream_queue: The queue storing event streams.
  '''
  def __init__(self):
    self._database = None
    self._log_watcher = None
    self._worker_processes = []
    self._event_blob_queue = None
    self._event_stream_queue = None

  def Init(self):
    '''Initializes Minijack.'''
    # Ignore Ctrl-C for all processes. The main process will be changed later.
    # We don't want Ctrl-C to break the sub-process works. The terminations of
    # sub-processes are controlled by the main process.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Pick the default event log dir depending on factory run or chroot run.
    event_log_dir = SHOPFLOOR_DATA_DIR
    if not os.path.exists(event_log_dir) and (
        'CROS_WORKON_SRCROOT' in os.environ):
      event_log_dir = os.path.join(
          os.environ['CROS_WORKON_SRCROOT'],
          'src', 'platform', 'factory', 'shopfloor_data')

    # TODO(waihong): Add more options for customization.
    # TODO(waihong): Use hacked_argparse.py which is helpful for args parsing.
    parser = optparse.OptionParser()
    parser.add_option('--event_log_dir', dest='event_log_dir', type='string',
                      metavar='PATH', default=event_log_dir,
                      help='path of the event log dir (default: %default)')
    parser.add_option('--event_log_db', dest='event_log_db', type='string',
                      metavar='PATH', default=EVENT_LOG_DB_FILE,
                      help='path of the event log db file (default: %default)')
    parser.add_option('--minijack_db', dest='minijack_db', type='string',
                      metavar='PATH', default=MINIJACK_DB_FILE,
                      help='path of the Minijack db file (default: %default)')
    parser.add_option('--log', dest='log', type='string', metavar='PATH',
                      help='write log to this file instead of stderr')
    parser.add_option('-i', '--interval', dest='interval', type='int',
                      default=DEFAULT_WATCH_INTERVAL,
                      help='log-watching interval in sec (default: %default)')
    parser.add_option('-j', '--jobs', dest='jobs', type='int',
                      default=DEFAULT_JOB_NUMBER,
                      help='jobs to load events parallelly (default: %default)')
    parser.add_option('-s', '--queue_size', dest='queue_size', type='int',
                      metavar='SIZE', default=DEFAULT_QUEUE_SIZE,
                      help='max size of the queue (default: %default)')
    parser.add_option('-v', '--verbose', action='count', dest='verbose',
                      help='increase message verbosity')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet',
                      help='turn off verbose messages')

    (options, args) = parser.parse_args()
    if args:
      parser.error('Invalid args: %s' % ' '.join(args))

    verbosity_map = {0: logging.INFO,
                     1: logging.DEBUG}
    verbosity = verbosity_map.get(options.verbose or 0, logging.NOTSET)
    log_format = '%(asctime)s %(levelname)s '
    if options.verbose > 0:
      log_format += '(%(filename)s:%(lineno)d) '
    log_format += '%(message)s'

    log_config = {'level': verbosity,
                  'format': log_format}
    if options.log:
      log_config.update({'filename': options.log})
    logging.basicConfig(**log_config)

    if options.quiet:
      logging.disable(logging.INFO)

    if not os.path.exists(options.event_log_dir):
      logging.error('Event log directory "%s" does not exist\n',
                    options.event_log_dir)
      parser.print_help()
      sys.exit(os.EX_NOINPUT)

    if options.jobs < 1:
      logging.error('Job number should be larger than or equal to 1.\n')
      parser.print_help()
      sys.exit(os.EX_NOINPUT)

    # TODO(waihong): Study the performance impact of the queue max size.
    maxsize = options.queue_size
    self._event_blob_queue = multiprocessing.JoinableQueue(maxsize)
    self._event_stream_queue = multiprocessing.JoinableQueue(maxsize)

    logging.debug('Init event log watcher, interval = %d', options.interval)
    self._log_watcher = EventLogWatcher(
        options.interval,
        event_log_dir=options.event_log_dir,
        event_log_db_file=options.event_log_db,
        handle_event_logs_callback=self.HandleEventLogs)

    logging.debug('Init event loading workers, jobs = %d', options.jobs)
    self._worker_processes = [multiprocessing.Process(
          target=EventLoadingWorker(options.event_log_dir),
          args=(self._event_blob_queue, self._event_stream_queue)
        ) for _ in range(options.jobs)]

    logging.debug('Init event receiving workers')
    self._database = db.Database()
    self._database.Init(options.minijack_db)
    self._worker_processes.append(multiprocessing.Process(
        target=EventReceivingWorker(self._database),
        args=(self._event_stream_queue,)))

  def Destory(self):
    '''Destorys Minijack.'''
    logging.info('Stopping event log watcher...')
    if self._log_watcher and self._log_watcher.IsThreadStarted():
      self._log_watcher.StopWatchThread()
    logging.info('Emptying all queues...')
    for queue in (self._event_blob_queue, self._event_stream_queue):
      if queue:
        queue.join()
    logging.info('Terminating all worker processes...')
    for process in self._worker_processes:
      if process:
        process.terminate()
        process.join()
    if self._database:
      self._database.Close()
      self._database = None
    logging.info('Minijack is shutdown gracefully.')

  def HandleEventLogs(self, log_name, chunk):
    '''Callback for event log watcher.'''
    logging.info('Get new event logs (%s, %d bytes)', log_name, len(chunk))
    blob = EventBlob({'log_name': log_name}, chunk)
    self._event_blob_queue.put(blob)

  def Main(self):
    '''The main Minijack logic.'''
    self.Init()
    logging.debug('Start the subprocesses and the event log watcher thread')
    for process in self._worker_processes:
      process.daemon = True
      process.start()
    self._log_watcher.StartWatchThread()

    # Exit main process when receiving Ctrl-C or a default kill signal.
    signal_handler = lambda signum, frame: sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.pause()

if __name__ == '__main__':
  minijack = Minijack()
  try:
    minijack.Main()
  finally:
    minijack.Destory()
