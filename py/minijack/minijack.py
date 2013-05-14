#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
Minijack is a real-time log converter for on-site factory log analysis.

It runs in the same device of the shopfloor service and keeps monitoring
the event log directory. When new logs come, it converts these event logs
and dumps them to a database, such that factory engineers can easily analyse
these logs using SQL queries.

This file starts a Minijack process which services forever until an user
presses Ctrl-C to terminate it. To use it, invoke as a standalone program:
  ./minijack [options]
"""

import logging
import multiprocessing
import optparse
import os
import signal
import sys
import time

import factory_common  # pylint: disable=W0611
from cros.factory.event_log_watcher import EventLogWatcher
from cros.factory.minijack import db
from cros.factory.minijack.datatypes import EventBlob, EventPacket
from cros.factory.minijack.workers import IdentityWorker, EventLoadingWorker
from cros.factory.test import utils


SHOPFLOOR_DATA_DIR = 'shopfloor_data'
EVENT_LOG_DB_FILE = 'event_log_db'
MINIJACK_DB_FILE = 'minijack_db'

DEFAULT_WATCH_INTERVAL = 30  # seconds
DEFAULT_JOB_NUMBER = 6
DEFAULT_QUEUE_SIZE = 10


class EventSinker(object):
  """Event Sinker which invokes the proper exporters to sink events to database.

  TODO(waihong): Unit tests.

  Properties:
    _database: The database object.
    _all_exporters: A list of all registered exporters.
    _event_invokers: A dict of lists, where the event id as key and the list
                     of handler functions as value.
  """
  def __init__(self, database):
    self._database = database
    self._all_exporters = []
    self._event_invokers = {}
    self.RegisterDefaultExporters()

  def RegisterDefaultExporters(self):
    """Registers the default exporters."""
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
        self.RegisterExporter(exporter)

  def RegisterExporter(self, exporter):
    """Registers a exporter object."""
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

  def SinkEventStream(self, stream):
    """Sinks the given event stream."""
    start_time = time.time()
    for event in stream:
      packet = EventPacket(stream.metadata, stream.preamble, event)
      self.SinkEventPacket(packet)
    logging.info('Sinked to database (%s, %d events, %.3f sec)',
                 stream.metadata.get('log_name'),
                 len(stream),
                 time.time() - start_time)

  def SinkEventPacket(self, packet):
    """Sinks the given event packet."""
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


class Minijack(object):
  """The main Minijack flow.

  TODO(waihong): Unit tests.

  Properties:
    _database: The database object.
    _log_watcher: The event log watcher.
    _worker_processes: A list of worker processes.
    _event_blob_queue: The queue storing event blobs.
    _event_stream_queue: The queue storing event streams.
  """
  def __init__(self):
    self._database = None
    self._log_watcher = None
    self._worker_processes = []
    self._event_blob_queue = None
    self._event_stream_queue = None

  def Init(self):
    """Initializes Minijack."""
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
        handle_event_logs_callback=self.HandleEventLogs,
        num_log_per_callback=50)

    logging.debug('Init event loading workers, jobs = %d', options.jobs)
    self._worker_processes = [multiprocessing.Process(
          target=EventLoadingWorker(options.event_log_dir),
          kwargs=dict(
            input_reader=iter(self._event_blob_queue.get, None),
            output_writer=lambda stream: (
              self._event_stream_queue.put(stream) if stream else None,
              self._event_blob_queue.task_done()))
        ) for _ in range(options.jobs)]

    logging.debug('Init event sinking workers')
    self._database = db.Database()
    self._database.Init(options.minijack_db)
    try:
      sinker = EventSinker(self._database)
    except db.DatabaseException as e:
      logging.exception('Error on initializing database: %s', str(e))
      sys.exit(os.EX_DATAERR)

    self._worker_processes.append(multiprocessing.Process(
        target=IdentityWorker(),
        kwargs=dict(
          input_reader=iter(self._event_stream_queue.get, None),
          output_writer=lambda stream: (
            sinker.SinkEventStream(stream),
            self._event_stream_queue.task_done(),
            # TODO(waihong): Move the queue monitoring to the main loop such
            # that it has better controls to create/terminate processes.
            self.CheckQueuesEmpty()))))

  def Destory(self):
    """Destorys Minijack."""
    logging.info('Stopping event log watcher...')
    if self._log_watcher and self._log_watcher.IsThreadStarted():
      self._log_watcher.StopWatchThread()
    logging.info('Emptying all queues...')
    for queue in (self._event_blob_queue, self._event_stream_queue):
      if queue:
        queue.join()
    logging.info('Terminating all worker processes...')
    for process in self._worker_processes:
      if process and process.is_alive():
        process.terminate()
        process.join()
    if self._database:
      self._database.Close()
      self._database = None
    logging.info('Minijack is shutdown gracefully.')

  def HandleEventLogs(self, chunk_info):
    """Callback for event log watcher."""
    for log_name, chunk in chunk_info:
      logging.info('Get new event logs (%s, %d bytes)', log_name, len(chunk))
      blob = EventBlob({'log_name': log_name}, chunk)
      self._event_blob_queue.put(blob)

  def CheckQueuesEmpty(self):
    """Checks queues empty to info users Minijack is idle."""
    if all((self._event_blob_queue.empty(), self._event_stream_queue.empty())):
      logging.info('Minijack is idle.')

  def Main(self):
    """The main Minijack logic."""
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
