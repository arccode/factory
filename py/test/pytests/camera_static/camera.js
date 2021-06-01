// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const imageDiv = document.getElementById('test-image');
const promptDiv = document.getElementById('prompt');
const overlayCanvas = document.getElementById('overlay');

const showImage = (data_url) => {
  imageDiv.src = data_url;
};

const hideImage = () => {
  document.getElementById('flex-container').classList.add('hidden');
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

const canvasToDataURL = async (canvas) => {
  const blob = await canvas.convertToBlob({type: 'image/jpeg'});
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.readAsDataURL(blob);
  });
};

class CameraTest {
  constructor(options) {
    this.facingMode = options.facingMode;
    this.width = options.width;
    this.height = options.height;
    this.flipImage = options.flipImage;
    this.videoStartPlayTimeoutMs = options.videoStartPlayTimeoutMs;
    this.videoStream = null;

    // The width/height would be set to the true width/height in grabFrame.
    this.canvas = new OffscreenCanvas(this.width, this.height);
    this.videoElem = document.getElementById('test-video');
    // We use the video element only on e2e mode.
    imageDiv.classList.add('hidden')
    this.videoElem.classList.remove('hidden');
    this.videoElem.classList.toggle('flip', this.flipImage);
    this.videoElemReadyForStreamCallback = null;

    this.videoElem.addEventListener('play', () => {
      if (this.videoElemReadyForStreamCallback !== null) {
        this.videoElemReadyForStreamCallback();
        this.videoElemReadyForStreamCallback = null;
      }
    });
    this.videoElem.autoplay = true;
  }

  async enable() {
    this.videoStream = await this.getVideoStreamTrack();
  }

  disable() {
    if (this.videoStream) {
      this.videoStream.stop();
      this.videoStream = null;
    }
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
    // Try to wait until |videoElem| starts to play so that |grabFrame|
    // can capture the data from it.
    // We expect the pytest invokes the API properly, this method shouldn't
    // be called before the previous call finishes.
    console.assert(this.videoElemReadyForStreamCallback === null);
    await new window.Promise((resolve, reject) => {
      // Fails if the |play| event is not raised in time.
      const timeoutId = window.setTimeout(() => {
        if (this.videoElemReadyForStreamCallback !== null) {
          this.videoElemReadyForStreamCallback = null;
          reject(new Error('timeout from video element'));
        }
      }, this.videoStartPlayTimeoutMs);
      this.videoElemReadyForStreamCallback = () => {
        window.clearTimeout(timeoutId);
        resolve();
      };
      this.videoElem.srcObject = mediaStream;
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
    this.canvas.width = this.videoElem.videoWidth;
    this.canvas.height = this.videoElem.videoHeight;
    this.canvas.getContext('2d').drawImage(this.videoElem, 0, 0);
  }

  // TODO(pihsun): Can use JavaScript API FaceDetector / BarcodeDetector on
  // frontend to avoid sending image back to backend in e2e mode after those
  // APIs are implemented by desktop Chrome.
  async grabFrameAndTransmitBack() {
    await this.grabFrame();
    const blobBase64 = (await canvasToDataURL(this.canvas))
                           .replace(/^data:image\/jpeg;base64,/, '');
    const goofy = test.invocation.goofy;
    const path = await goofy.sendRpc('UploadTemporaryFile', blobBase64);
    return path;
  }

  /**
   * Clear the overlay canvas.
   */
  clearOverlay() {
    const ctx = overlayCanvas.getContext('2d');
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  }

  /**
   * Draw a rectangle on the overlay canvas.
   * The size and coordinate of the rectangle are all in [0, 1] as relative to
   * the canvas size, so it's independent to the display size of the image.
   *
   * @param {number} x the x coordinate of the rectangle.
   * @param {number} y the y coordinate of the rectangle.
   * @param {number} w the width of the rectangle.
   * @param {number} h the height of the rectangle.
   */
  drawRect(x, y, w, h) {
    const ctx = overlayCanvas.getContext('2d');
    const {width, height} = overlayCanvas;
    x *= width;
    y *= height;
    w *= width;
    h *= height;

    ctx.beginPath();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'white';
    if (this.flipImage) {
      ctx.rect(overlayCanvas.width - x, y, -w, h);
    } else {
      ctx.rect(x, y, width, height);
    }
    ctx.stroke();
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
