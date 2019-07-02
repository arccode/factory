/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/**
 * The base class of all tests in `src/tests/` directory.
 */
import {TestState} from '/src/tests/test_state.js';
import {UiUtils} from '/src/utils/ui_utils.js';

export class TestCase {
  constructor() {
    this.html = '/src/tests/default.html';
    this.name = 'Default Test Name';
    this.state = TestState.UNTESTED;
    this.testItem = null;
  }

  /** Returns the name of the test case. */
  getTestName() {
    return this.name;
  }

  /** Set the test list item. */
  setTestItem(testItem) {
    this.testItem = testItem;
  }

  /** Set the test state */
  setTestState(testState) {
    this.state = testState;
    if (this.testItem !== null) {
      UiUtils.removeClassesWithPrefix(this.testItem, 'test-state-');
      this.testItem.classList.add(`test-state-${this.state.toLowerCase()}`);
    }
  }

  /** Called before runTest. */
  async setUp() {
    await this.setHTML();
  }

  /** Test case entry point. */
  async runTest() {}

  /** Called after runTest (no matter passed or not). */
  tearDown() {
    this.clearHTML();
  }

  async setHTML() {
    const response = await fetch(this.html);
    const html = await response.text();
    document.getElementById('setting').innerHTML = html;
  }

  clearHTML() {
    document.getElementById('setting').innerHTML = '';
  }

  failTest(message) {
    throw message;
  }
}
