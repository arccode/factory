// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const imageDiv = document.getElementById('test-image');
const promptDiv = document.getElementById('prompt');

const showImage = (data_url) => {
  imageDiv.src = data_url;
};

const hideImage = (hide) => {
  imageDiv.classList.toggle('hidden', hide);
};

const getErrorMessage = (error) => `${error.name}: ${error.message}`;

// TODO(pihsun): Move this to util.js
const runJSPromise = (js, eventName) => {
  eval(js).then((data) => {
    test.sendTestEvent(eventName, {data});
  }).catch((error) => {
    test.sendTestEvent(eventName, {error: getErrorMessage(error)});
  });
};

const runJS = (js, eventName) => {
  try {
    const data = eval(js);
    test.sendTestEvent(eventName, {data});
  } catch (error) {
    test.sendTestEvent(eventName, {error: getErrorMessage(error)});
  }
};

const showInstruction = (instruction) => {
  goog.dom.safe.setInnerHtml(
      promptDiv, cros.factory.i18n.i18nLabel(instruction));
};

class CameraTest {
  constructor(options) {
    this.facingMode = options.facingMode;
    this.width = options.width;
    this.height = options.height;
    this.flipImage = options.flipImage;
    this.videoStream = null;
    this.imageCapture = null;
    this.canvas = document.createElement('canvas');
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
    // Sometimes when the system is buzy, the videoStream become muted.
    // Restarting the stream solves the issue.
    if (this.videoStream.muted) {
      this.disable();
      await this.enable();
    }
    const frame = await this.imageCapture.grabFrame();
    this.canvas.width = frame.width;
    this.canvas.height = frame.height;
    this.canvas.getContext('2d').drawImage(frame, 0, 0);
    frame.close();
  }

  async grabFrameAndTransmitBack(data_event_name) {
    // Since there are some size limits for Goofy event size, and the frame
    // grabbed is usually about 100K+ in base64 in size, we need to segment it
    // and reconstruct in camera.py.
    await this.grabFrame();
    const blob = this.canvas.toDataURL('image/jpeg')
                     .replace(/^data:image\/jpeg;base64,/, '');
    const sliceLength = 50000;
    for (let idx = 0; idx < blob.length; idx += sliceLength) {
      const slice = blob.substr(idx, sliceLength);
      test.sendTestEvent(data_event_name, slice);
    }
  }

  async detectFaces() {
    const faceDetector = new FaceDetector({maxDetectedFaces: 1});
    const faces = await faceDetector.detect(this.canvas);
    if (!faces.length) {
      return false;
    }
    const ctx = this.canvas.getContext('2d');
    ctx.lineWidth = 4;
    ctx.strokeStyle = 'white';
    for (let face of faces) {
      ctx.rect(face.x, face.y, face.width, face.height);
      ctx.stroke();
    }
    return true;
  }

  async scanQRCode() {
    const barcodeDetector = new BarcodeDetector({formats: ['qr_code']});
    const codes = await barcodeDetector.detect(this.canvas);
    if (!codes.length) {
      return null;
    }
    return codes[0].rawValue;
  }

  showImage(ratio) {
    const tempCanvas = document.createElement('canvas');
    const {width, height} = this.canvas;
    const newWidth = Math.round(width * ratio);
    const newHeight = Math.round(height * ratio);
    tempCanvas.width = newWidth;
    tempCanvas.height = newHeight;
    const ctx = tempCanvas.getContext('2d');
    if (this.flipImage) {
      // We flip the image horizontally so the image looks like a mirror.
      ctx.scale(-1, 1);
      ctx.drawImage(
          this.canvas, 0, 0, width, height, -newWidth, 0, newWidth, newHeight);
    } else {
      ctx.drawImage(
          this.canvas, 0, 0, width, height, 0, 0, newWidth, newHeight);
    }
    showImage(tempCanvas.toDataURL('image/jpeg'));
  }
}

const exports = {
  showImage,
  hideImage,
  runJSPromise,
  runJS,
  showInstruction,
  CameraTest
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
