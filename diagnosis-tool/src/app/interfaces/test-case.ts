/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/**
 * The base class of all tests in `src/app/tests/` directory.
 */
export abstract class TestCase {
  /** The test argument for current test instance. */
  args: object = {};

  /** Called before runTest. */
  setUp(args: object = {}): void {
    this.args = args;
  }

  /** Called after runTest (no matter passed or not). */
  tearDown(): void {}

  /** Main test function. */
  abstract runTest(): void;

  /** Returns the name of the test case. */
  abstract getTestName(): string;
}
