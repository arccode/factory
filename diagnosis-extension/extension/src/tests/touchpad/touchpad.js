/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';

export class TouchpadTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/touchpad/touchpad.html';
    this.name = 'Touchpad';
    this.countTarget = 5;
    this.keyDown = this.keyDown.bind(this);
    this.handleClick = this.handleClick.bind(this);
    this.handleScroll = this.handleScroll.bind(this);
    this.handleDoubleClick = this.handleDoubleClick.bind(this);
  }

  async setUp() {
    this.clickCount = 0;
    this.dblClickCount = 0;
    this.countPassedTest = 0;
    this.isScrolled = false;
    this.enteredTest = false;

    await this.setHTML();
    document.addEventListener('keydown', this.keyDown);
    this.initTouchScrollTables(document.getElementById('container'));
    this.setEndTestPromise();
  }

  async runTest() {
    // The test requires human interaction, so we just wait for the test to end.
    const result = await this.waitEndTestResult();
    if (!result.success) {
      this.failTest(result.message);
    }
  }

  initTouchScrollTables(container) {
    const createElem = (tag, id, text, className) => {
      const element = document.createElement(tag);
      element.id = id;
      if (text) element.textContent = text;
      if (className) element.classList.add(className);
      return element;
    };

    const scroll = createElem('div', 'scroll', 'scroll');
    container.appendChild(scroll);
    for (const button of ['click', 'dblclick']) {
      const span = createElem('span', `${button}-text`, '0 / 0');
      const clickButton = createElem(
        'div', `${button}-button`, button, 'click-button');
      const div = createElem('div', button);
      div.append(span, clickButton);
      container.append(div);
    }
  }

  keyDown(e) {
    if (!this.enteredTest && e.key === ' ') {
      this.initTouchEvent();
      this.enteredTest = true;
    } else if (this.enteredTest && e.key === 'q') {
      this.endTest(false, 'Mark failed by operator.');
    }
  }

  initTouchEvent() {
    document.getElementById('scroll')
      .addEventListener('wheel', this.handleScroll);
    document.getElementById('click-button')
      .addEventListener('click', this.handleClick);
    document.getElementById('dblclick-button')
      .addEventListener('dblclick', this.handleDoubleClick);
  }

  removeTouchEvent() {
    document.removeEventListener('keydown', this.keyDown);
    document.getElementById('scroll')
      .removeEventListener('wheel', this.handleScroll);
    document.getElementById('click-button')
      .removeEventListener('click', this.handleClick);
    document.getElementById('dblclick-button')
      .removeEventListener('dblclick', this.handleDoubleClick);
  }

  handleScroll() {
    if (!this.isScrolled) {
      this.markTestCompleted('scroll');
      this.endTest(true);
    }
    this.isScrolled = true;
  }

  handleClick() {
    if (this.clickCount < this.countTarget) {
      this.clickCount += 1;
      document.getElementById('click-text').textContent =
        `${this.clickCount} / ${this.countTarget}`;
      if (this.clickCount === this.countTarget) {
        this.markTestCompleted('click-button');
        this.endTest(true);
      }
    }
  }

  handleDoubleClick() {
    if (this.dblClickCount < this.countTarget) {
      this.dblClickCount += 1;
      document.getElementById('dblclick-text').textContent =
        `${this.dblClickCount} / ${this.countTarget}`;
      if (this.dblClickCount === this.countTarget) {
        this.markTestCompleted('dblclick-button');
        this.endTest(true);
      }
    }
  }

  markTestCompleted(elementId) {
    const element = document.getElementById(elementId);
    element.classList.add('success');
  }

  endTest(success, message) {
    if (success) {
      this.countPassedTest += 1;
      if (this.countPassedTest < 3) return;
    }
    this.removeTouchEvent();
    this.sendEndTestResult(success, message);
  }
}