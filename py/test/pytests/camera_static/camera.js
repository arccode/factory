// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const getImageDiv = () => document.getElementById('camera-test-image');
const getPromptDiv = () => document.getElementById('camera-test-prompt');

const showJpegImage = (jpeg_binary) => {
  const element = getImageDiv();
  if (element) {
    element.src = 'data:image/jpeg;base64,' + jpeg_binary;
  }
};

const hideImage = (hide) => {
  const element = getImageDiv();
  if (element) {
    element.style.display = hide ? 'none' : '';
  }
};

const failWithError = (reason) => {
  if (reason.name != null && reason.message != null) {
    test.fail(`${reason.name}: ${reason.message}`);
  } else {
    test.fail(reason.toString());
  }
};

// TODO(pihsun): Move this to util.js
const runPromise = (promise, eventName) => {
  promise.then((data) => {
    test.sendTestEvent(eventName, data);
  }).catch(failWithError);
};

const setupUI = () => {
  const state = document.getElementById('state');
  state.appendChild(goog.dom.createDom('img', {'id': 'camera-test-image'}));
  state.appendChild(goog.dom.createDom('div', {'id': 'camera-test-prompt'}));
  state.appendChild(goog.dom.createDom('div', {'id': 'camera-test-timer'}));
};

const showInstruction = (instruction) => {
  goog.dom.safe.setInnerHtml(
      getPromptDiv(), cros.factory.i18n.i18nLabel(instruction));
};

const setupCamera = (options) => {
  window.camera = new Camera(options);
};

class Camera {
  constructor(options) {
    this.facingMode = options.facingMode;
    this.width = options.width;
    this.height = options.height;
    this.videoStream = null;
    this.imageCapture = null;
  }

  async enable() {
    this.videoStream = await this.getVideoStreamTrack();
    this.imageCapture = new ImageCapture(this.videoStream);
  }

  disable() {
    if (this.videoStream) {
      this.videoStream.stop();
      this.videoStream = null;
    }
    this.imageCapture = null;
  }

  async checkPermission() {
    await this.enable();
    this.disable();
  }

  async getVideoStreamTrack() {
    const mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        width: this.width,
        height: this.height,
        facingMode: {exact: this.facingMode}
      }
    });
    return mediaStream.getVideoTracks()[0];
  }

  async grabFrame() {
    return await this.imageCapture.grabFrame();
  }

  async grabFrameAndTransmitBack(data_event_name) {
    // Since there are some size limits for Goofy event size, and the frame
    // grabbed is usually about 100K+ in base64 in size, we need to segment it
    // and reconstruct in camera.py.
    const frame = await this.grabFrame();
    const {width, height} = frame;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(frame, 0, 0);
    const blob =
        canvas.toDataURL('image/jpeg').replace(/^data:image\/jpeg;base64,/, '');
    const sliceLength = 50000;
    for (let idx = 0; idx < blob.length; idx += sliceLength) {
      const slice = blob.substr(idx, sliceLength);
      test.sendTestEvent(data_event_name, slice);
    }
  }
}

const exports = {
  showJpegImage,
  hideImage,
  failWithError,
  runPromise,
  setupUI,
  showInstruction,
  setupCamera
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
