# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A very simple WebRTC-based camera test.

This test requires the user to click "Allow" to permit access to the camera,
since there is presently no API to disable this access check.
"""

import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils

_MSG_TIME_REMAINING = lambda time: i18n_test_ui.MakeI18nLabelWithClass(
    'Time remaining: {time}', 'camera-test-info', time=time)
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
    'prompt1': i18n_test_ui.MakeI18nLabel(
        'Click "Allow" at the top of the screen.'),
    'prompt2': i18n_test_ui.MakeI18nLabel(
        'Click <a href="javascript:test.pass()">pass</a> or '
        '<a href="javascript:test.fail()">fail</a>.'),
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
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS_CAMERA_TEST)
    self.template.SetState(_HTML_CAMERA_TEST)
    self.ui.RunJS(_JS_WEBRTC_CAMERA)
    self.ui.EnablePassFailKeys()
    process_utils.StartDaemonThread(target=self.CountdownTimer)

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
