/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/**
 * The base class of all tests in `src/tests/` directory.
 */
export class TestCase {
  constructor() {
    this.html = '/src/tests/default.html';
    this.name = 'Default Test Name';
  }

  /** Returns the name of the test case. */
  getTestName() {
    return this.name;
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
}
