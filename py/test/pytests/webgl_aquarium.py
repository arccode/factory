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
    '<link rel="stylesheet" type="text/css" href="goofy_webgl_aquarium.css">'
    '<iframe src="/tests/{0}/aquarium.html", width="100%", height="100%"'
    ' id="webgl-aquarium"></iframe>')

_JS_WEBGL_AQUARIUM = """
var cls_fullscreen = 'goofy-aquarium-full-screen';

function getWebGlFrame() {
  return document.getElementById('webgl-aquarium');
}

function hideOptions() {
  var top_ui = getWebGlFrame().contentDocument.getElementById('topUI');
  if (!top_ui) {
    return 0;
  }
  top_ui.style.display = 'none';
}

function enableFullScreen() {
  window.test.setFullScreen(true);
  getWebGlFrame().classList.add(cls_fullscreen);
}

function disableFullScreen() {
  getWebGlFrame().classList.remove(cls_fullscreen);
  window.test.setFullScreen(false);
}

function toggleFullScreen() {
  var webgl_iframe = getWebGlFrame();
  var toggle_btn = webgl_iframe.contentDocument
    .getElementById('fullscreen_toggle');

  if (webgl_iframe.classList.contains(cls_fullscreen)) {
    disableFullScreen();
  }
  else {
    enableFullScreen();
  }
}

function updateUI(time_left, hide_options) {
  var webgl_iframe = getWebGlFrame();
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

    var fullscreen_btn = document.createElement('button');
    fullscreen_btn.id = 'fullscreen_toggle';
    fullscreen_btn.style.fontSize = '1.5em';
    fullscreen_btn.innerHTML = "Toggle Full Screen";
    fullscreen_btn.onclick = toggleFullScreen;

    var timer_div = document.createElement('div');
    timer_div.style.color = 'white';
    timer_div.style.fontSize = '2em';
    timer_div.innerHTML = 'Time left: ';
    timer_span = document.createElement('span');
    timer_span.id = 'timer';
    timer_div.appendChild(timer_span);

    var goofy_addon = document.createElement('div');
    goofy_addon.appendChild(fullscreen_btn)
    goofy_addon.appendChild(timer_div)

    // First child is the fps.
    fps_container.childNodes[1].style.fontSize = '2em';
    fps_container.insertBefore(goofy_addon, fps_container.childNodes[1]);
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
          default=True),
      Arg('full_screen', bool, 'Whether to go full screen mode by default',
          default=False)
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.template.SetState(_HTML_WEBGL_AQUARIUM.format(self.ui.test))
    self.ui.RunJS(_JS_WEBGL_AQUARIUM)
    self.end_time = time.time() + self.args.duration_secs
    process_utils.StartDaemonThread(target=self.PeriodicCheck)

    if self.args.full_screen:
      self.ui.RunJS('enableFullScreen();')

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
