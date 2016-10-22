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
import os
import shutil
import tempfile
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg


_DEFAULT_INTERVAL = 1
_DEFAULT_NUM_EVENTS = 2
_DEFAULT_EVENT_NAME = 'instalog'
_DEFAULT_NUM_ATTACHMENTS = 0
_DEFAULT_ATTACHMENT_BYTES = 1 * 1024 * 1024  # 1mb


class InputTime(plugin_base.InputPlugin):

  ARGS = [
      Arg('interval', (int, float), 'Interval in between events.',
          optional=True, default=_DEFAULT_INTERVAL),
      Arg('num_events', int, 'Number of events to produce on every interval.',
          optional=True, default=_DEFAULT_NUM_EVENTS),
      Arg('event_name', (str, unicode), 'Name of the event.',
          optional=True, default=_DEFAULT_EVENT_NAME),
      Arg('num_attachments', int, 'Number of files to attach to each event.',
          optional=True, default=_DEFAULT_NUM_ATTACHMENTS),
      Arg('attachment_bytes', int, 'Size in bytes of each attachment file.',
          optional=True, default=_DEFAULT_ATTACHMENT_BYTES),
  ]

  def SetUp(self):
    """Sets up the plugin."""
    # Create the temporary directory for attachments.
    self._tmp_dir = tempfile.mkdtemp(prefix='input_time_')
    self.info('Temporary directory for attachments: %s', self._tmp_dir)

  def TearDown(self):
    """Tears down the plugin."""
    # Remove the temporary directory.
    shutil.rmtree(self._tmp_dir)

  def Main(self):
    """Main thread of the plugin."""
    batch_id = 0
    # Check to make sure plugin should still be running.
    while not self.IsStopping():
      # Try to emit an event.
      self.debug('Trying to emit %d events', self.args.num_events)
      events = []
      for i in range(self.args.num_events):
        # Create fake attachment files for the event.
        attachments = {}
        for j in range(self.args.num_attachments):
          att_path = os.path.join(self._tmp_dir, '%d_%d_%d' % (batch_id, i, j))
          with open(att_path, 'wb') as f:
            f.write(os.urandom(self.args.attachment_bytes))
          attachments[j] = att_path

        # Data for the event.
        data = {'name': self.args.event_name,
                'batch_id': batch_id,
                'id': i,
                'timestamp': datetime.datetime.now()}

        # Create the event.
        events.append(datatypes.Event(data, attachments))

      self.info('Emitting batch #%d with %d events',
                batch_id, self.args.num_events)
      if not self.Emit(events):
        self.error('Failed to emit %d events, dropping', self.args.num_events)
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)

      # Sleep until next emit interval.
      self.debug('Sleeping for %s', self.args.interval)
      self.Sleep(self.args.interval)
      batch_id += 1


if __name__ == '__main__':
  plugin_base.main()
