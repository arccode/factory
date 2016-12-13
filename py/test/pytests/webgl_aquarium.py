# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""WebGL performance test that executes a set of WebGL operations."""

import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


_HTML_WEBGL_AQUARIUM = (
    '<iframe src="/tests/{0}/aquarium.html", width="100%", height="100%"'
    ' id="webgl-aquarium"></iframe>')

_JS_WEBGL_AQUARIUM = """
function hideOptions() {
  var webgl_iframe = document.getElementById('webgl-aquarium');
  var top_ui = webgl_iframe.contentDocument.getElementById('topUI');
  if (!top_ui) {
    return 0;
  }
  top_ui.style.display = 'none';
}

function updateUI(time_left, hide_options) {
  var webgl_iframe = document.getElementById('webgl-aquarium');
  var timer_span = webgl_iframe.contentDocument.getElementById('timer');

  if (!timer_span) {
    var fps_container = webgl_iframe.contentDocument.getElementsByClassName(
      'fpsContainer')[0];
    if (!fps_container) {
      return 0;
    }

    if (hide_options) {
      hideOptions();
    }

    timer_span = document.createElement('span');
    timer_span.id = 'timer';

    var timer_div = document.createElement('div');
    timer_div.style.color = 'white';
    timer_div.style.fontSize = '2em';
    timer_div.innerHTML = 'Time left: ';
    timer_div.appendChild(timer_span);

    // First child is the fps.
    fps_container.childNodes[1].style.fontSize = '2em';
    fps_container.insertBefore(timer_div, fps_container.childNodes[1]);
  }

  timer_span.innerHTML = time_left;
}

function registerContextLostHandler() {
  var webgl_iframe = document.getElementById('webgl-aquarium');
  var canvas = webgl_iframe.contentDocument.getElementById('canvas');
  webgl_iframe.contentWindow.onload =
      webgl_iframe.contentWindow.tdl.webgl.registerContextLostHandler(
          canvas, function() {
              window.test.fail(
                  'Lost WebGL context.' +
                  ' Did you switch to VT2 for more than 10 seconds?')});
}

window.onload = registerContextLostHandler;
"""


class WebglAquarium(unittest.TestCase):
  ARGS = [
      Arg('duration_secs', int, 'Duration of time in seconds to run the test',
          default=60),
      Arg('hide_options', bool, 'Whether to hide the options on UI',
          default=True)
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.template.SetState(_HTML_WEBGL_AQUARIUM.format(self.ui.test))
    self.ui.RunJS(_JS_WEBGL_AQUARIUM)
    self.end_time = time.time() + self.args.duration_secs
    process_utils.StartDaemonThread(target=self.PeriodicCheck)

  def FormatSeconds(self, secs):
    hours = int(secs / 3600)
    minutes = int((secs / 60) % 60)
    seconds = int(secs % 60)
    return '%02d:%02d:%02d' % (hours, minutes, seconds)

  def PeriodicCheck(self):
    while True:
      time_left = self.end_time - time.time()
      if time_left <= 0:
        break
      self.ui.CallJSFunction(
          'updateUI', self.FormatSeconds(time_left),
          self.args.hide_options)
      time.sleep(1)
    self.ui.Pass()

  def runTest(self):
    self.ui.Run()
