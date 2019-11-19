# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import audio_utils
from cros.factory.utils.arg_utils import Arg

DEFAULT_SECONDS = 10


class VideoPlaybackTest(test_case.TestCase):
  """Video Playback Test."""
  ui_class = test_ui.UI
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
  ]

  def runTest(self):
    logging.info('Video Playback test started')
    logging.info('video_file=[%s]', self.args.video_file)
    logging.info('time_limit=%s secs', self.args.time_limit)
    audio_utils.CRAS().EnableOutput()
    audio_utils.CRAS().SetActiveOutputNodeVolume(100)
    self.ui.CallJSFunction('init', self.args.video_file, self.args.loop,
                           self.args.time_limit, self.args.show_controls)
    self.WaitTaskEnd()
