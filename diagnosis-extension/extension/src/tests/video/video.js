/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';

export class VideoTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/video/video.html';
    this.name = 'Video';
    this.videoPath = 'src/tests/video/project-fi.mp4';
    this.keyDown = this.keyDown.bind(this);
    this.playVideo = this.playVideo.bind(this);
    this.successTest = this.successTest.bind(this);
    this.hideVideo = this.hideVideo.bind(this);
  }

  async setUp() {
    this.enteredTest = false;
    await this.setHTML();
    this.videoElem = document.getElementById('test-video');
    this.videoElem.hidden = true;
    this.passTestButton = document.getElementById('pass-test');
    this.passTestButton.hidden = true;
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

  keyDown(e) {
    if (!this.enteredTest && e.key === ' ') {
      this.enteredTest = true;
      this.playVideo();
      this.initEventListener();
    } else if (this.enteredTest && e.key === 'q') {
      this.endTest(false, 'Mark failed by operator.');
    }
  }

  initEventListener() {
    this.passTestButton.addEventListener('click', this.successTest);
    this.videoElem.addEventListener('ended', this.hideVideo);
  }

  removeEventListner() {
    document.removeEventListener('keydown', this.keyDown);
    this.passTestButton.removeEventListener('click', this.successTest);
    this.videoElem.removeEventListener('ended', this.hideVideo);
  }

  playVideo() {
    chrome.runtime.getPackageDirectoryEntry((dirEntry) => {
      const successCallback = (fileEntry) => {
        fileEntry.file((file) => {
          const fileURL = window.URL.createObjectURL(file);
          this.videoElem.hidden = false;
          this.videoElem.src = fileURL;
        });
      };
      const errorCallback = (error) => {
        this.endTest(false, error);
      };
      dirEntry.getFile(
          this.videoPath, undefined, successCallback, errorCallback);
    });
    this.passTestButton.hidden = false;
  }

  successTest() {
    this.endTest(true);
  }

  hideVideo() {
    this.videoElem.hidden = true;
  }

  endTest(success, message) {
    this.removeEventListner();
    this.sendEndTestResult(success, message);
  }
}