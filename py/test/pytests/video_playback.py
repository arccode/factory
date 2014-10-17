# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test.args import Arg

DEFAULT_SECONDS = 10


class VideoPlaybackTest(unittest.TestCase):
  '''Video Playback Test.'''
  ARGS = [
    Arg('video_file', str,
        'Relative path to load the video.',
        default='', optional=True),
    Arg('loop', bool,
        'Whether we want to loop the video.',
        default=False, optional=True),
    Arg('time_limit', int,
        'Seconds to force terminate the test.',
        default=DEFAULT_SECONDS, optional=True),
    Arg('show_controls', bool,
        'Whether we want to show the control UI.',
        default=False, optional=True),
  ]

  def runTest(self):
    logging.info('Video Playback test started')
    logging.info('video_file=[%s]', self.args.video_file)
    logging.info('time_limit=%s secs', self.args.time_limit)
    ui = test_ui.UI()
    ui.CallJSFunction('init',
                      self.args.video_file,
                      self.args.loop,
                      self.args.time_limit,
                      self.args.show_controls)
    ui.Run()
    logging.info('Video Playback test finished')
