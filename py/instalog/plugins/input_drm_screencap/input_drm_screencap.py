#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input screen capture plugin.

Logs screenshots of the framebuffer every interval.
"""

from __future__ import print_function

import datetime

import instalog_common  # pylint: disable=unused-import
from instalog import datatypes
from instalog import plugin_base
from instalog.plugins.input_drm_screencap import drm
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils


_DEFAULT_INTERVAL = 60


class InputFramebuf(plugin_base.InputPlugin):

  ARGS = [
      Arg('interval', (int, float), 'Interval in between screen captures.',
          default=_DEFAULT_INTERVAL),
  ]

  def EmitScreencap(self):
    """Emits a screenshot event."""
    self.debug('Capturing screenshot...')
    screencap_image = drm.screenshot()
    self.debug('Done capturing, writing to disk...')

    screencap_path = file_utils.CreateTemporaryFile(
        prefix='screencap_', suffix='.png')
    screencap_image.save(screencap_path, optimize=True)
    self.debug('Done writing to disk')

    # Data for the event.
    data = {
        '__screencap__': True,
        'time': datetime.datetime.utcnow(),
    }

    # Attachments for the event.
    attachments = {
        'screencap.png': screencap_path,
    }

    # Create the event.
    screencap_event = datatypes.Event(data, attachments)

    self.info('Emitting screencap event')
    if not self.Emit([screencap_event]):
      self.error('Failed to emit health event, dropping')

  def Main(self):
    """Main thread of the plugin."""
    # Check to make sure plugin should still be running.
    while not self.IsStopping():
      try:
        self.EmitScreencap()
      except Exception:
        self.exception('Exception encountered when creating screencap')

      # Sleep until next emit interval.
      self.debug('Sleeping for %s', self.args.interval)
      self.Sleep(self.args.interval)


if __name__ == '__main__':
  plugin_base.main()
