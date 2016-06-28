#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output stdout plugin.

A sample output plugin that writes events to stdout.
"""

from __future__ import print_function

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils.arg_utils import Arg


_DEFAULT_STREAM_TIMEOUT = 5
_DEFAULT_STREAM_COUNT = 5


class OutputStdout(plugin_base.OutputPlugin):

  ARGS = [
      Arg('stream_timeout', (int, float), 'Timeout for each EventStream.',
          optional=True, default=_DEFAULT_STREAM_TIMEOUT),
      Arg('stream_count', (int, float), 'Count for each EventStream.',
          optional=True, default=_DEFAULT_STREAM_COUNT),
  ]

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      event_stream = self.NewStream()
      if not event_stream:
        continue

      # Get all current events from the EventStream object.
      events = []
      # TODO: Figure out bug when no timeout specified.
      for event in event_stream.iter(timeout=self.args.stream_timeout,
                                     count=self.args.stream_count):
        events.append(event)
        self.debug('len(events) = %d', len(events))

      # Print to stdout.
      for event in events:
        print(event.Serialize())

      # Commit these events.
      success_string = 'success' if event_stream.Commit() else 'failure'
      self.info('Committed %d events: %s', len(events), success_string)


if __name__ == '__main__':
  plugin_base.main()
