/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';
import {LoggingUtils} from '/src/utils/logging_utils.js';
import {TimeUtils} from '/src/utils/time_utils.js';

export class KeyboardTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/keyboard/keyboard.html';
    this.name = 'Keyboard';
    this.layoutArray = ['ANSI', 'ISO', 'JIS'];
    this.keyDown = this.keyDown.bind(this);
    this.getLayout = this.getLayout.bind(this);
    this.keyDead = this.keyDead.bind(this);
  }

  async setUp() {
    this.remainingTime = 60;  // Default to 60 seconds
    this.testArray = new Set();  // All remaining keys needed to be pushed
    this.enteredTest = false;
    this.deadKeys = [];
    this.layout = null;
    await this.setHTML();
    this.setEndTestPromise();
  }

  async runTest() {
    document.getElementById('setup').hidden = true;
    document.getElementById('keyboard-test').hidden = true;
    document.addEventListener('keydown', this.keyDown);

    // The test requires human interaction, so we just wait for the test to end.
    const result = await this.waitEndTestResult();
    if (!result.success) {
      this.failTest(result.message);
    }
  }

  async setTestTimeout() {
    const timeout = 0.01;
    while (this.remainingTime >= 0) {
      await TimeUtils.delay(timeout);
      this.remainingTime -= timeout;
      document.getElementById('time').textContent =
          this.remainingTime.toFixed(1);
    }
    if (this.enteredTest) {
      this.endTest(false, 'Time out');
    }
  }

  setUpLayout() {
    const setup = document.getElementById('setup');
    for (const layout of this.layoutArray) {
      const div = document.createElement('div');
      div.id = layout;
      div.classList.add('layout-style');
      const p = document.createElement('p');
      p.textContent = `${layout} Layout`;
      const img = document.createElement('img');
      img.src = `src/tests/keyboard/${layout}.png`;
      div.append(p, img);
      setup.appendChild(div);
    }
  }

  initClickListener() {
    for (const layout of this.layoutArray) {
      document.getElementById(layout).addEventListener('click', this.getLayout);
    }
  }

  removeClickListener() {
    for (const layout of this.layoutArray) {
      document.getElementById(layout)
          .removeEventListener('click', this.getLayout);
    }
  }

  getLayout(e) {
    this.layout = e.target.parentNode.id;
    if (this.layoutArray.includes(this.layout)) {
      document.getElementById('setup').hidden = true;
      document.getElementById('keyboard-test').hidden = false;

      this.removeClickListener();
      document.getElementById('keyboard-keys')
          .addEventListener('click', this.keyDead);
      this.getBindingFile();
      this.setTestTimeout();
    }
  }

  getBindingFile() {
    const bindingFileName = `src/tests/keyboard/${this.layout}.json`;
    chrome.runtime.getPackageDirectoryEntry((dirEntry) => {
      const successCallback = (fileEntry) => {
        fileEntry.file((file) => {
          const reader = new FileReader();
          reader.onloadend = () => {
            this.setUpTestBoard(reader.result);
          }
          reader.readAsText(file);
        });
      };
      const errorCallback = (error) => {
        this.endTest(false, error);
      };
      dirEntry.getFile(
          bindingFileName, undefined, successCallback, errorCallback);
    });
  }

  setUpTestBoard(binding) {
    this.binding = JSON.parse(binding);
    const keyContainer = document.getElementById('keyboard-keys');
    // Chrome blocked web from changing standard action of top-row.
    const skippedKeys = [
      'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10',
      'F13', 'CapsLock'
    ];
    for (const keycode of Object.keys(this.binding)) {
      const [left, top, width, height] = this.binding[keycode];
      const div = document.createElement('div');
      div.dataset.keycode = keycode;
      div.textContent = keycode;
      div.style.left = `${left}px`;
      div.style.top = `${top}px`;
      div.style.width = `${width}px`;
      div.style.height = `${height}px`;

      div.classList.add('keyboard-test-key');
      this.testArray.add(keycode);
      keyContainer.appendChild(div);
      if (skippedKeys.includes(keycode)) {
        this.markKeyState(keycode, 'skipped');
      }
    }

    const container = document.getElementById('keyboard-test-image');
    const img = new Image();
    img.id = 'layout-image';
    img.src = `src/tests/keyboard/${this.layout}.png`;
    img.onload = () => {
      const xOffset = (container.clientWidth - img.width) / 2;
      keyContainer.style.left = xOffset;
    };
    container.appendChild(img);
  }

  keyDown(e) {
    if (!this.enteredTest && e.key === ' ') {
      this.enteredTest = true;
      document.getElementById('setup').hidden = false;
      this.setUpLayout();
      this.initClickListener();
      return;
    } else if (this.enteredTest && this.layout) {
      if (this.testArray.has(e.code)) {
        this.markKeyState(e.code, 'tested');
      }
      this.checkFinished();
    }
    e.preventDefault();
  }

  keyDead(e) {
    const keycode = e.target.dataset.keycode;
    this.markKeyState(keycode, 'down');
    this.deadKeys.push(keycode);
    this.checkFinished();
  }

  checkFinished() {
    if (this.testArray.size === 0) {
      if (this.deadKeys.length === 0) {
        this.endTest(true);
      }
      this.endTest(false, 'exist dead keys.');
    }
  }

  markKeyState(keycode, state) {
    for (const div of document.querySelectorAll(
             `.keyboard-test-key[data-keycode="${keycode}"]`)) {
      div.classList.forEach((className) => {
        if (className.startsWith("state-")) {
          div.classList.remove(className);
        }
      });
      div.classList.add(`state-${state}`);
      // The shape of Enter key in ISO layout is a concave hexagon.
      if (keycode === 'Enter' && this.layout === 'ISO') {
        const enter = document.createElement('div');
        enter.classList.add('keyboard-test-key', `state-${state}`, 'iso-enter');
        document.getElementById('keyboard-keys').appendChild(enter);
      }
    }
    this.testArray.delete(keycode);
  }

  endTest(success, message) {
    if (this.deadKeys.length > 0) {
      LoggingUtils.log(
        `Keyboard: ${this.deadKeys} is marked dead by operator.`);
    }
    document.getElementById('keyboard-keys')
        .removeEventListener('click', this.keyDead);
    document.removeEventListener('keydown', this.keyDown);
    this.sendEndTestResult(success, message);
  }
}