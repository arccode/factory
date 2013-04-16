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

import imp
import logging
import optparse
import os
import pprint
import re
import signal
import sqlite3
import sys
import yaml
from Queue import Queue

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import EVENT_LOG_DIR
from cros.factory.event_log_watcher import EventLogWatcher
from cros.factory.event_log_watcher import EVENT_LOG_DB_FILE
from cros.factory.test import factory
from cros.factory.test import utils

MINIJACK_DB_FILE = os.path.join(factory.get_state_root(), 'minijack_db')
DEFAULT_WATCH_INTERVAL = 30  # seconds
DEFAULT_QUEUE_SIZE = 10
EVENT_DELIMITER = '---\n'

# The following YAML strings needs further handler. So far we just simply
# remove them. It works well now, while tuples are treated as lists, unicodes
# are treated as strings, objects are dropped.
# TODO(waihong): Use yaml.add_multi_constructor to handle them.
YAML_STR_BLACKLIST = [
  r' !!python/tuple',
  r' !!python/unicode',
  r' !!python/object[A-Za-z_.:/]+',
]

class EventList(list):
  '''Event List Structure.

  This is a list to store multiple non-preamble events, which share
  the same preamble event.

  TODO(waihong): Unit tests.

  Properties:
    preamble: The dict of the preamble event.
  '''
  def __init__(self, yaml_str):
    '''Initializer.

    Args:
      yaml_str: The string contains multiple yaml-formatted events.
    '''
    super(EventList, self).__init__()
    self.preamble = None
    self._load_from_yaml(yaml_str)

  def _load_from_yaml(self, yaml_str):
    '''Loads from multiple yaml-formatted events with delimiters.

    Args:
      yaml_str: The string contains multiple yaml-formatted events.
    '''
    events_str = yaml_str.split(EVENT_DELIMITER)
    for event_str in events_str:
      # Some expected patterns appear in the log. Remove them.
      for regex in YAML_STR_BLACKLIST:
        event_str = re.sub(regex, '', event_str)
      try:
        event = yaml.safe_load(event_str)
      except yaml.YAMLError, e:
        logging.exception('Error on parsing the yaml string "%s": %s',
                          event_str, e)

      if event is None:
        continue
      if event['EVENT'] == 'preamble':
        self.preamble = event
      else:
        self.append(event)

class EventReceiver(object):
  '''Event Receiver which invokes the proper parsers when events is received.

  TODO(waihong): Unit tests.

  Properties:
    _conn: The connection object of the database.
    _all_parsers: A list of all registered parsers.
    _event_invokers: A dict of lists, where the event id as key and the list
                     of handler functions as value.
  '''
  def __init__(self, conn):
    self._conn = conn
    self._all_parsers = []
    self._event_invokers = {}

  def register_parser(self, parser):
    '''Registers a parser object.'''
    logging.debug('Register the parser: %s', parser)
    self._all_parsers.append(parser)
    # Search all handle_xxx() methods in the parser instance.
    for handler_name in dir(parser):
      if handler_name.startswith('handle_'):
        event_id = handler_name.split('_', 1)[1]
        # Create a new list if not present.
        if event_id not in self._event_invokers:
          self._event_invokers[event_id] = []
        # Add the handler function to the list.
        handler_func = getattr(parser, handler_name)
        self._event_invokers[event_id].append(handler_func)

    logging.debug('Call the setup method of the parser: %s', parser)
    parser.setup()

  def receive_events(self, event_list):
    '''Callback for an event list received.'''
    # Drop the event list if its preamble not exist.
    # TODO(waihong): Remove this drop once all events in the same directory.
    if event_list.preamble is None:
      logging.warn('Drop the event list without preamble.')
      return
    for event in event_list:
      self.receive_event(event_list.preamble, event)

  def receive_event(self, preamble, event):
    '''Callback for an event received.'''
    # Event id 'all' is a special case, which means the handlers accepts
    # all kinds of events.
    for event_id in ('all', event['EVENT']):
      invokers = self._event_invokers.get(event_id, [])
      for invoker in invokers:
        invoker(preamble, event)

  def cleanup(self):
    '''Clearns up all the parsers.'''
    for parser in self._all_parsers:
      parser.cleanup()

class Minijack(object):
  '''The main Minijack flow.

  TODO(waihong): Unit tests.

  Properties:
    _conn: The connection object of the database.
    _event_receiver: The event receiver.
    _log_dir: The path of the event log directory.
    _log_watcher: The event log watcher.
    _queue: The queue storing event lists.
  '''
  def __init__(self):
    self._conn = None
    self._event_receiver = None
    self._log_dir = None
    self._log_watcher = None
    # TODO(waihong): Study the performance impact of the queue max size.
    self._queue = Queue(DEFAULT_QUEUE_SIZE)

  def init(self):
    '''Initializes Minijack.'''
    # Exit this program when receiving Ctrl-C.
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

    # TODO(waihong): Add more options for customization.
    # TODO(waihong): Use hacked_argparse.py which is helpful for args parsing.
    parser = optparse.OptionParser()
    parser.add_option('--event_log_dir', dest='event_log_dir', type='string',
                      metavar='PATH', default=EVENT_LOG_DIR,
                      help='path of the event log directory')
    parser.add_option('--event_log_db', dest='event_log_db', type='string',
                      metavar='FILE', default=EVENT_LOG_DB_FILE,
                      help='file name of the event log db')
    parser.add_option('--minijack_db', dest='minijack_db', type='string',
                      metavar='FILE', default=MINIJACK_DB_FILE,
                      help='file name of the Minijack db')
    parser.add_option('--log', dest='log', type='string', metavar='PATH',
                      help='write log to this file instead of stderr')
    parser.add_option('-i', '--interval', dest='interval', type='int',
                      default=DEFAULT_WATCH_INTERVAL,
                      help='log-watching interval in sec (default: %default)')
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

    logging.debug('Connect to the database: %s', options.minijack_db)
    self._conn = sqlite3.connect(options.minijack_db)
    # Make sqlite3 always return bytestrings for the TEXT data type.
    self._conn.text_factory = str
    self._event_receiver = EventReceiver(self._conn)

    logging.debug('Load all the default parsers')
    parser_pkg = imp.load_module('parser', *imp.find_module('parser'))
    # Find all parser modules named xxx_parser.
    for parser_name in dir(parser_pkg):
      if parser_name.endswith('_parser'):
        parser_module = getattr(parser_pkg, parser_name)
        # Class name conversion: XxxParser.
        class_name = ''.join([s.capitalize() for s in parser_name.split('_')])
        parser_class = getattr(parser_module, class_name)
        parser = parser_class(self._conn)
        # Register the parser instance.
        self._event_receiver.register_parser(parser)

    logging.debug('Start event log watcher, interval = %d', options.interval)
    self._log_watcher = EventLogWatcher(
        options.interval,
        event_log_dir=options.event_log_dir,
        event_log_db_file=options.event_log_db,
        handle_event_logs_callback=self.handle_event_logs)
    self._log_dir = options.event_log_dir
    self._log_watcher.StartWatchThread()

  def destroy(self):
    '''Destorys Minijack.'''
    if self._log_watcher:
      logging.debug('Destory event log watcher')
      if self._log_watcher.IsThreadStarted():
        self._log_watcher.StopWatchThread()
      self._log_watcher = None
    self._queue.join()
    if self._event_receiver:
      logging.debug('Clear-up event receiver')
      self._event_receiver.cleanup()
    if self._conn:
      self._conn.close()

  def _get_preamble_from_log_file(self, log_name):
    '''Gets the preamble event dict from a given log file name.'''
    # TODO(waihong): Optimize it using a cache.
    try:
      events_str = open(os.path.join(self._log_dir, log_name)).read()
    except:  # pylint: disable=W0702
      logging.exception('Error on reading log file %s: %s',
                        log_name,
                        utils.FormatExceptionOnly())
      return None
    events = EventList(events_str)
    if not events.preamble:
      # TODO(waihong): Check the yesterday-directory with the same log_name.
      logging.warn('The log file does not have a preamble event: %s', log_name)
    return events.preamble

  def handle_event_logs(self, log_name, chunk):
    '''Callback for event log watcher.'''
    logging.info('Get new event logs (%s, %d bytes)', log_name, len(chunk))
    events = EventList(chunk)
    if not events.preamble:
      events.preamble = self._get_preamble_from_log_file(log_name)
    logging.debug('Preamble: \n%s', pprint.pformat(events.preamble))
    logging.debug('Event List: \n%s', pprint.pformat(events))
    # Put the event list into the queue.
    self._queue.put(events)

  def main(self):
    '''The main Minijack logic.'''
    self.init()
    ONE_YEAR = 365 * 24 * 60 * 60
    while True:
      # TODO(waihong): Try to use multiple threads to dequeue and see any
      # performance gain.

      # Work-around of a Python bug that blocks Ctrl-C.
      #   http://bugs.python.org/issue1360
      events = self._queue.get(timeout=ONE_YEAR)
      logging.debug('Disptach the event list to the receiver.')
      try:
        self._event_receiver.receive_events(events)
      except:  # pylint: disable=W0702
        logging.exception('Error on invoking the event lists: %s',
                          utils.FormatExceptionOnly())
      self._queue.task_done()

if __name__ == '__main__':
  minijack = Minijack()
  try:
    minijack.main()
  finally:
    minijack.destroy()
