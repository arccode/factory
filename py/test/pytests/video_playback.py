# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.test import test_case
from cros.factory.test.utils import audio_utils
from cros.factory.utils.arg_utils import Arg

DEFAULT_SECONDS = 10

class VideoPlaybackTest(test_case.TestCase):
  """Video Playback Test."""
  ARGS = [
      Arg('video_file', str,
          'Relative path to load the video.',
          default=''),
      Arg('loop', bool,
          'Whether we want to loop the video.',
          default=False),
      Arg('time_limit', int,
          'Seconds to force terminate the test.',
          default=DEFAULT_SECONDS),
      Arg('show_controls', bool,
          'Whether we want to show the control UI.',
          default=False),
      Arg('audio_device', str,
          'Name of audio input device.',
          default=''),
      Arg('video_device', str,
          'Name of video input device.',
          default='')
  ]

  def runTest(self):
    self.assertFalse(self.args.video_file and
                     (self.args.video_device or self.args.audio_device),
                     'May not request both an input device and file')

    logging.info('Video Playback test started')
    if self.args.video_file:
      logging.info('video_file=[%s]', self.args.video_file)
    else:
      logging.info('video_device=%s', self.args.video_device)
      logging.info('audio_device=%s', self.args.audio_device)
    logging.info('time_limit=%s secs', self.args.time_limit)
    audio_utils.CRAS().EnableOutput()
    audio_utils.CRAS().SetActiveOutputNodeVolume(100)
    self.ui.CallJSFunction('init', self.args.video_file,
                           self.args.audio_device, self.args.video_device,
                           self.args.loop, self.args.time_limit,
                           self.args.show_controls)
    self.WaitTaskEnd()
