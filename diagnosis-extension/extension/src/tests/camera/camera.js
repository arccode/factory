/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';

export class CameraTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/camera/camera.html';
    this.name = 'Camera';
    this.keyDown = this.keyDown.bind(this);
    this.grabFrame = this.grabFrame.bind(this);
    this.passTest = this.passTest.bind(this);
  }

  async setUp() {
    this.enteredTest = false;
    this.videoStream = null;
    await this.setHTML();
    this.videoElem = document.getElementById('video');
    this.passTestButton = document.getElementById('pass-test');
    this.passTestButton.hidden = true;
    this.takePictureButton = document.getElementById('take-picture');
    this.takePictureButton.hidden = true;
    this.canvas = document.getElementById('canvas');
    this.canvas.hidden = true;
    document.addEventListener('keydown', this.keyDown);
    this.setEndTestPromise();
  }

  async runTest() {
    // The test requires human interaction, so we just wait for the test to end.
    const result = await this.waitEndTestResult();
    if (!result.success) {
      this.failTest(result.message);
    }
  }

  async keyDown(e) {
    if (!this.enteredTest && e.key === ' ') {
      await this.enableCamera();
      this.enteredTest = true;
      this.takePictureButton.hidden = false;
      this.passTestButton.hidden = false;
      this.initEventListener();
    } else if (this.enteredTest && e.key === 'q') {
      this.endTest(false, 'Mark failed by operator.');
    }
  }

  async enableCamera() {
    try {
      const constraints = {audio: true, video: true};
      const media = await navigator.mediaDevices.getUserMedia(constraints);
      this.videoElem.srcObject = media;
      this.videoStream = media.getVideoTracks()[0];
    } catch (error) {
      this.endTest(false, error);
    }
  }

  disableCamera() {
    if (this.videoStream) {
      this.videoStream.stop();
      this.videoStream = null;
      this.videoElem.srcObject = null;
    }
  }

  initEventListener() {
    this.takePictureButton.addEventListener('click', this.grabFrame);
    this.passTestButton.addEventListener('click', this.passTest);
  }

  removeEventListner() {
    document.removeEventListener('keydown', this.keyDown);
    this.takePictureButton.removeEventListener('click', this.grabFrame);
    this.passTestButton.removeEventListener('click', this.passTest);
  }

  async grabFrame() {
    // Sometimes when the system is busy, the videoStream become muted.
    // Restarting the stream solves the issue.
    if (this.videoStream.muted) {
      this.disableCamera();
      await this.enableCamera();
    }
    this.canvas.hidden = false;
    this.canvas.width = this.videoElem.videoWidth;
    this.canvas.height = this.videoElem.videoHeight;
    this.canvas.getContext('2d').drawImage(this.videoElem, 0, 0);
  }

  passTest() {
    this.endTest(true);
  }

  endTest(success, message) {
    this.disableCamera();
    this.removeEventListner();
    this.sendEndTestResult(success, message);
  }
}