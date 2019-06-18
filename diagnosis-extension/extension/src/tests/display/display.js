/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';
import {LoggingUtils} from '/src/utils/logging_utils.js'
import {TimeUtils} from '/src/utils/time_utils.js'

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
    this.inTest = true;
    this.testScreenState = 'HIDE';
    this.runningTestIndex = 0;

    await this.setHTML();
    this.setColorTable(this.colors);
    this.setColor();

    this.keyDown = this.keyDown.bind(this);
    document.addEventListener('keydown', this.keyDown);
  }

  async runTest() {
    // The test requires human interaction, so we just wait for the test to end.
    await this.waitTestFinish();
  }

  /** Returns a promise that resolves when the test ends. */
  async waitTestFinish() {
    // Polling every 0.5 seconds.
    const timeout = 500;
    while (this.inTest) {
      await TimeUtils.delay(timeout);
    }
  }

  keyDown(e) {
    if (e.code === 'Space') {
      this.testScreenState = 'SHOW';
    } else if (e.code === 'Enter') {
      if (this.runningTestIndex + 1 < this.colors.length) {
        this.runningTestIndex += 1;
      } else {
        this.endTest(true, '');
      }
    } else if (e.code === 'Escape') {
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
    const fullMessage = `${this.name} ${success ? 'succeeded' : 'failed'}` +
                         `${message ? ': ' + message : '.'}`;
    LoggingUtils.log(fullMessage);
    this.inTest = false;
  }
}
