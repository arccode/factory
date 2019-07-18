/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';
import {UiUtils} from '/src/utils/ui_utils.js';

/**
 * Display test.
 */
export class DisplayTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/display/display.html';
    this.name = 'Display';
    this.colors = [
      'darkgray',
      'gray',
      'dimgray',
      'red',
      'green',
      'blue'
    ];
  }

  setColorTable(colors) {
    const table = document.getElementById('color-table');
    const row = table.insertRow(-1);
    for (let i in colors) {
      const cell = row.insertCell(-1);
      cell.innerText = colors[i];
    }
  }

  async setUp() {
    this.testScreenState = 'HIDE';
    this.runningTestIndex = 0;

    await this.setHTML();
    this.setColorTable(this.colors);
    this.setColor();

    this.keyDown = this.keyDown.bind(this);
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
    if (e.code === 'Space') {
      this.testScreenState = 'SHOW';
      UiUtils.requestFullscreen();
    } else if (e.code === 'Enter') {
      if (this.runningTestIndex + 1 < this.colors.length) {
        this.runningTestIndex += 1;
      } else {
        this.endTest(true, '');
      }
    } else if (e.code === 'KeyQ') {
      if (this.testScreenState === 'SHOW') {
        this.endTest(
          false, `Failed on ${this.colors[this.runningTestIndex]} test.`);
      }
    }
    this.setColor(this.colors[this.runningTestIndex]);
  }

  setColor(color) {
    const element = document.getElementById('color-display');
    if (!element) return;
    if (this.testScreenState === 'HIDE') {
      element.style.visibility = 'hidden';
    } else {
      element.style.visibility = 'visible';
      element.style.backgroundColor = color;
    }
  }

  endTest(success, message) {
    this.testScreenState = 'HIDE';
    this.setColor();
    document.removeEventListener('keydown', this.keyDown);
    this.sendEndTestResult(success, message);
  }

  tearDown() {
    UiUtils.exitFullscreen();
    this.clearHTML();
  }
}