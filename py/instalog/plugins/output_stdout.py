#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output stdout plugin.

A sample output plugin that writes events to stdout.
"""

from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg


_DEFAULT_BATCH_SIZE = 5
_DEFAULT_TIMEOUT = 5


class OutputStdout(plugin_base.OutputPlugin):

  ARGS = [
      Arg('batch_size', int, 'How many events to queue before printing.',
          default=_DEFAULT_BATCH_SIZE),
      Arg('timeout', (int, float), 'Timeout to print without full batch.',
          default=_DEFAULT_TIMEOUT),
  ]

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      event_stream = self.NewStream()
      if not event_stream:
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)
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
      if events:
        self.info('Commit %d events', len(events))
      event_stream.Commit()


if __name__ == '__main__':
  plugin_base.main()
