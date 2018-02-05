// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const webglIFrame = document.getElementById('webgl-aquarium');

const iframeLoaded = new Promise((resolve) => {
  webglIFrame.contentWindow.addEventListener('load', resolve);
});

const getFpsContainer = () =>
    webglIFrame.contentDocument.getElementsByClassName('fpsContainer')[0];

const hideOptions = () => {
  const topUI = webglIFrame.contentDocument.getElementById('topUI');
  if (topUI) {
    topUI.style.display = 'none';
  }
};

const isFullScreen = () => webglIFrame.classList.contains('fullscreen');

const toggleFullScreen = () => {
  const fullscreen = !isFullScreen();

  webglIFrame.classList.toggle('fullscreen', fullscreen);
  window.test.setFullScreen(fullscreen);

  iframeLoaded.then(() => {
    const infoDiv = webglIFrame.contentDocument.getElementById('info');
    if (fullscreen) {
      infoDiv.style.display = 'none';
    } else {
      infoDiv.style.display = 'block';
      // fpsContainer is moved during updateUI().
      getFpsContainer().style.top = '10px';
    }
  });
};

const updateUI = (timeLeft, hideOption) => {
  const fpsContainer = getFpsContainer();
  if (!fpsContainer) {
    return;
  }

  let timerSpan = webglIFrame.contentDocument.getElementById('timer');
  if (!timerSpan) {
    if (hideOption) {
      hideOptions();
    }

    const fullscreenBtn = document.createElement('button');
    fullscreenBtn.style.fontSize = '1.5em';
    fullscreenBtn.innerText = 'Toggle Full Screen';
    fullscreenBtn.onclick = toggleFullScreen;

    const timerDiv = document.createElement('div');
    timerDiv.style.color = 'white';
    timerDiv.style.fontSize = '2em';
    timerDiv.innerText = 'Time left: ';
    timerSpan = document.createElement('span');
    timerSpan.id = 'timer';
    timerDiv.appendChild(timerSpan);

    const goofyAddon = document.createElement('div');
    goofyAddon.appendChild(fullscreenBtn);
    goofyAddon.appendChild(timerDiv);

    // First child is the fps.
    fpsContainer.childNodes[1].style.fontSize = '2em';
    fpsContainer.insertBefore(goofyAddon, fpsContainer.childNodes[1]);
  }

  timerSpan.innerText = timeLeft;

  if (isFullScreen()) {
    // Move FPS container (30px, 10px) to prevent screen burn-in.
    const sec = timeLeft.split(':').pop();
    fpsContainer.style.top = sec + '%';
  }
};

iframeLoaded.then(() => {
  const canvas = webglIFrame.contentDocument.getElementById('canvas');
  webglIFrame.contentWindow.tdl.webgl.registerContextLostHandler(
    canvas, () => {
      window.test.fail(
        'Lost WebGL context.' +
        ' Did you switch to VT2 for more than 10 seconds?');
    });
});

const exports = {
  toggleFullScreen,
  updateUI
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
