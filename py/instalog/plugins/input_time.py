#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input time plugin.

A sample input plugin that produces N events every I seconds.
"""

from __future__ import print_function

import datetime
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg


_DEFAULT_INTERVAL = 1
_DEFAULT_NUM_EVENTS = 1


class InputTime(plugin_base.InputPlugin):

  ARGS = [
      Arg('interval', (int, float), 'Interval in between events.',
          default=_DEFAULT_INTERVAL, optional=True),
      Arg('num_events', int, 'Number of events to produce on every interval.',
          default=_DEFAULT_NUM_EVENTS, optional=True),
      Arg('event_name', (str, unicode), 'Name of the event.',
          optional=False),
  ]

  def Main(self):
    """Main thread of the plugin."""
    # Check to make sure plugin should still be running.
    while not self.IsStopping():
      # Try to emit an event.
      self.debug('Trying to emit %d events', self.args.num_events)
      events = []
      for i in range(self.args.num_events):
        events.append(datatypes.Event({'name': self.args.event_name,
                                       'id': i,
                                       'timestamp': datetime.datetime.now()}))
      if not self.Emit(events):
        self.error('Failed to emit %d events, dropping', self.args.num_events)

      # Sleep until next emit interval.
      self.debug('Sleeping for %s', self.args.interval)
      time.sleep(self.args.interval)


if __name__ == '__main__':
  plugin_base.main()
