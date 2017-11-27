// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const webgl_iframe = document.getElementById('webgl-aquarium');

const getFpsContainer = () =>
    webgl_iframe.contentDocument.getElementsByClassName('fpsContainer')[0];

const hideOptions = () => {
  const top_ui = webgl_iframe.contentDocument.getElementById('topUI');
  if (top_ui) {
    top_ui.style.display = 'none';
  }
};

const enableFullScreen = () => {
  window.test.setFullScreen(true);
  webgl_iframe.classList.add('goofy-aquarium-full-screen');
  webgl_iframe.contentDocument.getElementById('info').style.display = 'none';
};

const disableFullScreen = () => {
  webgl_iframe.classList.remove('goofy-aquarium-full-screen');
  webgl_iframe.contentDocument.getElementById('info').style.display = 'block';
  // fpsContainer is moved during updateUI().
  getFpsContainer().style.top = '10px';
  window.test.setFullScreen(false);
};

const isFullScreen = () =>
    webgl_iframe.classList.contains('goofy-aquarium-full-screen');

const toggleFullScreen = () => {
  if (isFullScreen()) {
    disableFullScreen();
  } else {
    enableFullScreen();
  }
};

const updateUI = (time_left, hide_options) => {
  const fps_container = getFpsContainer();
  if (!fps_container) {
    return;
  }

  let timer_span = webgl_iframe.contentDocument.getElementById('timer');
  if (!timer_span) {
    if (hide_options) {
      hideOptions();
    }

    const fullscreen_btn = document.createElement('button');
    fullscreen_btn.style.fontSize = '1.5em';
    fullscreen_btn.innerText = 'Toggle Full Screen';
    fullscreen_btn.onclick = toggleFullScreen;

    const timer_div = document.createElement('div');
    timer_div.style.color = 'white';
    timer_div.style.fontSize = '2em';
    timer_div.innerText = 'Time left: ';
    timer_span = document.createElement('span');
    timer_span.id = 'timer';
    timer_div.appendChild(timer_span);

    const goofy_addon = document.createElement('div');
    goofy_addon.appendChild(fullscreen_btn);
    goofy_addon.appendChild(timer_div);

    // First child is the fps.
    fps_container.childNodes[1].style.fontSize = '2em';
    fps_container.insertBefore(goofy_addon, fps_container.childNodes[1]);
  }

  timer_span.innerText = time_left;

  if (isFullScreen()) {
    // Move FPS container (30px, 10px) to prevent screen burn-in.
    const sec = time_left.split(':').pop();
    fps_container.style.top = sec + '%';
  }
};

webgl_iframe.contentWindow.onload = () => {
  const canvas = webgl_iframe.contentDocument.getElementById('canvas');
  webgl_iframe.contentWindow.tdl.webgl.registerContextLostHandler(
    canvas, () => {
      window.test.fail(
        'Lost WebGL context.' +
        ' Did you switch to VT2 for more than 10 seconds?');
    });
};

const exports = {
  toggleFullScreen,
  updateUI
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
