# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A very simple WebRTC-based camera test.

This test requires the user to click "Allow" to permit access to the camera,
since there is presently no API to disable this access check.
"""

import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test import test_ui
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread

_MSG_TIME_REMAINING = lambda t: test_ui.MakeLabel(
    'Time remaining: %d' % t, u'剩余时间：%d' % t, 'camera-test-info')
_ID_IMAGE = 'camera-test-image'
_ID_PROMPT1 = 'camera-test-prompt1'
_ID_PROMPT2 = 'camera-test-prompt2'
_ID_COUNTDOWN_TIMER = 'camera-test-timer'

_HTML_CAMERA_TEST = """
    <video id="%(id_image)s" width="320" height="240" autoplay></video>
    <div id="%(id_prompt1)s" class="camera-test-info">
      %(prompt1)s
    </div>
    <div id="%(id_prompt2)s" class="camera-test-info" style="display: none">
      %(prompt2)s
    </div>
    <div id="%(id_timer)s"></div>
""" % {
    'id_image': _ID_IMAGE,
    'id_prompt1': _ID_PROMPT1,
    'id_prompt2': _ID_PROMPT2,
    'id_timer': _ID_COUNTDOWN_TIMER,
    'prompt1': test_ui.MakeLabel(
        'Click "Allow" at the top of the screen.',
        zh=u'点击上面的 "Allow" 按钮'),
    'prompt2': test_ui.MakeLabel(
        ('Click <a href="javascript:test.pass()">pass</a> or '
         '<a href="javascript:test.fail()">fail</a>.'),
        zh=(u'请点击： <a href="javascript:test.pass()">正常</a> 还是 '
            u'<a href="javascript:test.fail()">不正常</a>')),
}

_JS_WEBRTC_CAMERA = """
    var video = document.getElementById('%(id_image)s');
    navigator.webkitGetUserMedia({video: true},
        function(stream) {
          video.src = window.webkitURL.createObjectURL(stream);
          $('%(id_prompt1)s').style.display = 'none';
          $('%(id_prompt2)s').style.display = 'block';
        },
        function(err) {
          test.fail('Error from getUserMedia: ' + err.code);
        }
    );
""" % {
    'id_image': _ID_IMAGE,
    'id_prompt1': _ID_PROMPT1,
    'id_prompt2': _ID_PROMPT2,
}
_CSS_CAMERA_TEST = '.camera-test-info { font-size: 2em; }'


class WebrtcCameraTest(unittest.TestCase):
  ARGS = [
    Arg('timeout_secs', int, 'Timeout value for the test.', default=60),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_CAMERA_TEST)
    self.template.SetState(_HTML_CAMERA_TEST)
    self.ui.RunJS(_JS_WEBRTC_CAMERA)
    self.ui.EnablePassFailKeys()
    StartDaemonThread(target=self.CountdownTimer)

  def CountdownTimer(self):
    """Starts a countdown timer and fails the test if timer reaches zero."""
    time_remaining = self.args.timeout_secs
    while time_remaining > 0:
      self.ui.SetHTML(_MSG_TIME_REMAINING(time_remaining),
                      id=_ID_COUNTDOWN_TIMER)
      time.sleep(1)
      time_remaining -= 1
    self.ui.Fail('Camera test failed due to timeout.')

  def runTest(self):
    self.ui.Run()
