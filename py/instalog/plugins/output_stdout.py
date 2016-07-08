#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output stdout plugin.

A sample output plugin that writes events to stdout.
"""

from __future__ import print_function

import time

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils.arg_utils import Arg


_DEFAULT_BATCH_SIZE = 5
_DEFAULT_TIMEOUT = 5


class OutputStdout(plugin_base.OutputPlugin):

  ARGS = [
      Arg('batch_size', int, 'How many events to queue before printing.',
          optional=True, default=_DEFAULT_BATCH_SIZE),
      Arg('timeout', (int, float), 'Timeout to print without full batch.',
          optional=True, default=_DEFAULT_TIMEOUT),
  ]

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      event_stream = self.NewStream()
      if not event_stream:
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        time.sleep(1)
        continue

      # Get all current events from the EventStream object.
      events = []
      for event in event_stream.iter(timeout=self.args.timeout,
                                     count=self.args.batch_size):
        events.append(event)
        self.debug('len(events) = %d', len(events))

      # Print to stdout.
      for event in events:
        print(event.Serialize())

      # Commit these events.
      success_string = 'success' if event_stream.Commit() else 'failure'
      if len(events) > 0:
        self.info('Commit %d events: %s', len(events), success_string)


if __name__ == '__main__':
  plugin_base.main()
