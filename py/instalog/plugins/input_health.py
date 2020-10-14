#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input health plugin.

Logs system information about the machine to monitor its health.
"""

import datetime
import os

from cros.factory.instalog import datatypes
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils.arg_utils import Arg


_DEFAULT_INTERVAL = 20


class InputHealth(plugin_base.InputPlugin):

  ARGS = [
      Arg('interval', (int, float), 'Interval in between health events.',
          default=_DEFAULT_INTERVAL),
  ]

  @staticmethod
  def GetDiskUsage(path):
    st = os.statvfs(path)
    free = st.f_bavail * st.f_frsize
    total = st.f_blocks * st.f_frsize
    used = (st.f_blocks - st.f_bfree) * st.f_frsize
    return {
        'total': total,
        'used': used,
        'free': free
    }

  def Main(self):
    """Main thread of the plugin."""
    # Check to make sure plugin should still be running.
    while not self.IsStopping():
      # Data for the event.
      data = {
          '__health__': True,
          'systemTime': datetime.datetime.utcnow(),
          'diskUsage': self.GetDiskUsage(self.GetDataDir())
      }

      # Create the event.
      health_event = datatypes.Event(data, {})

      self.info('Emitting health event')
      if not self.Emit([health_event]):
        self.error('Failed to emit health event, dropping')
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)

      # Sleep until next emit interval.
      self.debug('Sleeping for %s', self.args.interval)
      self.Sleep(self.args.interval)


if __name__ == '__main__':
  plugin_base.main()
