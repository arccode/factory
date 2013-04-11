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
import signal
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.event_log_watcher import EventLogWatcher

DEFAULT_WATCH_INTERVAL = 30  # seconds

class Minijack(object):
  '''The main Minijack flow.

  TODO(waihong): Unit tests.

  Properties:
    _log_watcher: The event log watcher.
  '''
  def __init__(self):
    self._log_watcher = None

  def init(self):
    '''Initializes Minijack.'''
    # Exit this program when receiving Ctrl-C.
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

    # TODO(waihong): Add more options for customization.
    # TODO(waihong): Use hacked_argparse.py which is helpful for args parsing.
    parser = optparse.OptionParser()
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
        handle_event_logs_callback=self.handle_event_logs)
    self._log_watcher.StartWatchThread()

  def destroy(self):
    '''Destorys Minijack.'''
    if self._log_watcher:
      logging.debug('Destory event log watcher')
      if self._log_watcher.IsThreadStarted():
        self._log_watcher.StopWatchThread()
      self._log_watcher = None

  def handle_event_logs(self, log_name, chunk):
    '''Callback for event log watcher.'''
    # TODO(waihong): Implement the proper log to database convertion.
    logging.info('Get new event logs (%s, %d bytes)', log_name, len(chunk))
    logging.debug('Log Content: \n%s', chunk)

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
