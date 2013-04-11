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
import optparse
import os
import pprint
import re
import signal
import sys
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import EVENT_LOG_DIR
from cros.factory.event_log_watcher import EventLogWatcher
from cros.factory.event_log_watcher import EVENT_LOG_DB_FILE
from cros.factory.test import utils

DEFAULT_WATCH_INTERVAL = 30  # seconds
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

class Minijack(object):
  '''The main Minijack flow.

  TODO(waihong): Unit tests.

  Properties:
    _log_dir: The path of the event log directory.
    _log_watcher: The event log watcher.
  '''
  def __init__(self):
    self._log_dir = None
    self._log_watcher = None

  def init(self):
    '''Initializes Minijack.'''
    # Exit this program when receiving Ctrl-C.
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

    # TODO(waihong): Add more options for customization.
    # TODO(waihong): Use hacked_argparse.py which is helpful for args parsing.
    parser = optparse.OptionParser()
    parser.add_option('--event_log_dir', dest='event_log_dir', type='string',
                      default=EVENT_LOG_DIR,
                      help='path of the event log directory')
    parser.add_option('--event_log_db', dest='event_log_db', type='string',
                      default=EVENT_LOG_DB_FILE,
                      help='file name of the event log db')
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
    logging.basicConfig(level=verbosity, format=log_format)
    if options.quiet:
      logging.disable(logging.INFO)

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
    # TODO(waihong): Implement the proper log to database convertion.
    logging.info('Get new event logs (%s, %d bytes)', log_name, len(chunk))
    events = EventList(chunk)
    if not events.preamble:
      events.preamble = self._get_preamble_from_log_file(log_name)
    logging.debug('Preamble: \n%s', pprint.pformat(events.preamble))
    logging.debug('Event List: \n%s', pprint.pformat(events))

  def main(self):
    '''The main Minijack logic.'''
    self.init()
    while True:
      pass

if __name__ == '__main__':
  minijack = Minijack()
  try:
    minijack.main()
  finally:
    minijack.destroy()
